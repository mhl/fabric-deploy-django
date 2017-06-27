from __future__ import unicode_literals

from datetime import datetime
from os.path import join

from fabric.api import env, run, settings, sudo, cd
from fabric.tasks import Task
from fabric.utils import abort
from fabvenv import virtualenv


env.sudo_prefix += '-H '
env.use_ssh_config = True


class DjangoDeployTask(Task):
    name = 'deploy'

    unix_user = None
    site_root = None
    service_name = None
    repository_url = None
    repo_dir = None

    def run(self, committish, fake_initial_migrations='no'):
        if fake_initial_migrations not in ('yes', 'no'):
            abort("fake_initial_migrations must be either 'yes' or 'no' "
                  "(default is 'no')")

        with settings(sudo_user=self.unix_user):
            timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
            timestamp = timestamp.replace(':', '.')

            new_release_dir = join(self.site_root, 'releases', timestamp)
            new_repo_dir = join(new_release_dir, self.repo_dir)
            current_release_dir = join(self.site_root, 'releases', 'current')
            current_repo_dir = join(current_release_dir, self.repo_dir)
            sudo('mkdir -p {}'.format(new_release_dir))

            # Assume that the unix user has a deploy key for this repo - this
            # should be created by puppet and manually added to the repo
            if 0 == sudo('test -d {0}'.format(current_repo_dir), quiet=True).return_code:
                # In this case a previous deploy had succeeding in
                # cloning the repository, so we can save time and
                # bandwidth on each deploy by basing our new clone
                # on that
                self.local_clone(current_repo_dir, new_repo_dir)
            else:
                with cd(new_release_dir):
                    # Otherwise, we need to clone everything from scratch:
                    sudo('git clone -q --recursive {0}'.format(self.repository_url))

            self.checkout_committish(new_repo_dir, committish)

            with cd(new_repo_dir):
                short_commit = sudo('git rev-parse --short HEAD').strip()

            new_requirements = join(new_repo_dir, 'requirements.txt')
            current_requirements = join(current_repo_dir, 'requirements.txt')
            new_virtualenv_symlink = join(new_release_dir, 'virtualenv')

            if self.requirements_changed(current_requirements, new_requirements):
                # This means that either requirements.txt has changes or that this
                # is the first deploy and current_requirements doesn't exist. In
                # both cases we need to create a new virtualenv.
                new_virtualenv_dir = join(self.site_root, 'virtualenvs', short_commit)

                sudo("virtualenv --no-site-packages " + new_virtualenv_dir)

                sudo("ln -s {} {}".format(new_virtualenv_dir, new_virtualenv_symlink))
                with virtualenv(new_virtualenv_symlink):
                    sudo('pip install -U pip')
                    sudo('pip install -q -r ' + new_requirements)
                with cd(new_virtualenv_symlink):
                    sudo('npm install yuglify')
            else:
                # requirements.txt for the new release is the same as for the
                # current one, so we can re-use its virtualenv.
                current_virtualenv = sudo("readlink -n -f " + join(current_release_dir, 'virtualenv'))
                sudo("ln -s {} {}".format(current_virtualenv, new_virtualenv_symlink))

            with virtualenv(new_virtualenv_symlink):
                with cd(new_repo_dir):
                    # TODO: Should we be doing something special with settings at
                    # this point?
                    yuglify_bin_dir = join(new_virtualenv_symlink, 'node_modules', 'yuglify', 'bin')
                    sudo('export PATH="{}:$PATH" && ./manage.py collectstatic --noinput'.format(yuglify_bin_dir))

                    migrate_command = './manage.py migrate --noinput'
                    if fake_initial_migrations == 'yes':
                        migrate_command += ' --fake-initial'
                    sudo(migrate_command)

            # FIXME: we actually want to do this in a gunicorn pre_exec hook
            # -f and -n are needed to make sure that it overwrites the existing
            # 'current' symlink:
            sudo("ln -sfn {} {}".format(timestamp, current_release_dir))

        run("sudo service {0} restart".format(self.service_name))

        if env.host_string == 'asti':
            with settings(sudo_user=self.unix_user):
                with cd(new_repo_dir):
                    sudo('git push -f origin {}:refs/heads/deployed'.format(committish))

    def requirements_changed(self, current, new):
        diff_command = "diff {} {}".format(current, new)
        diff = sudo(diff_command, quiet=True)
        return diff.return_code != 0

    def local_clone(self, source_repo, destination_repo):
        '''Efficiently mirror a local non-bare repository

        This will clone source_repo to destination_repo (using
        hard-links in the object database, so it's efficient in disk
        space terms) but make sure that the origin remote's URL in
        destination_repo is the same as in source_repo (rather than it
        pointing to source_repo). It also recursively mirrors
        submodules from the existing respository.'''

        with settings(sudo_user=self.unix_user):
            sudo('git clone {0} {1}'.format(
                source_repo,
                destination_repo
            ))
            # Save the real origin URL of this repository:
            with cd(source_repo):
                origin_url = sudo('git config remote.origin.url')
            with cd(destination_repo):
                sudo('git remote set-url origin {0}'.format(origin_url))
                sudo('git submodule init')
                for line in sudo('git submodule status').splitlines():
                    fields = line.strip().split()
                    path = fields[1]
                    source_submodule = join(source_repo, path)
                    destination_submodule = join(destination_repo, path)
                    self.local_clone(source_submodule, destination_submodule)

    def checkout_committish(self, repo_directory, committish):
        '''Switch the given non-bare repository to committish

        The reason this is more complicated than:

            git checkout [committish]

        ... is that in every case we want to make sure it's
        up-to-date; in the case of a local branch that means fetching,
        and resetting it to its upstream branch.'''

        with settings(sudo_user=self.unix_user):
            with cd(repo_directory):
                # First, make sure that all the remote-tracking
                # branches are up-to-date:
                sudo('git fetch origin')
                # Try to resolve committish as a local branch:
                output = sudo('git rev-parse --verify refs/heads/{0}'.format(committish), quiet=True)
                if output.return_code == 0:
                    # Then committish is a local branch, and we
                    # can check it out and reset it to upstream:
                    sudo('git checkout {0}'.format(committish))
                    sudo('git reset --hard {0}@{{upstream}}'.format(committish))
                else:
                    # Then committish is presumably either:
                    #
                    #  (a) A remote-tracking branch, a tag, or an
                    #      object name (SHA1sum)
                    #
                    #  (b) A name ('foo', say) that corresponds to
                    #      a remote-tracking branch origin/foo
                    #
                    #  (c) Something else
                    #
                    # In the case of (a) this checkout will detach
                    # HEAD and point it to the committish - if it's a
                    # remote-tracking branch that will have been
                    # updated above.
                    #
                    # In the case of (b) this will use checkout's
                    # DWIM ('Do What I Mean') behaviour, creating
                    # a local branch called 'foo' based on
                    # 'origin/foo' and setting origin/foo as its
                    # upstream.
                    #
                    # In the case of (c) this will just fail and
                    # that's the best we can do.
                    sudo('git checkout {0}'.format(committish))
                sudo('git submodule update --init')
