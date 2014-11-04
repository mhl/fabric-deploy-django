from datetime import datetime
from os.path import join

from fabric.api import env, settings, sudo, cd
from fabric.tasks import Task
from fabvenv import virtualenv


env.sudo_prefix += '-H '
env.use_ssh_config = True

unix_user = 'example'
site_root = '/var/www/example.com'


class DeployTask(Task):
    name = 'deploy'
    def run(self, committish):
        with settings(sudo_user=unix_user):
            timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
            timestamp = timestamp.replace(':', '.')

            new_release_dir = join(site_root, 'releases', timestamp)
            new_repo_dir = join(new_release_dir, 'example-repository')
            current_release_dir = join(site_root, 'releases', 'current')
            current_repo_dir = join(current_release_dir, 'example-repository')
            sudo('mkdir -p {}'.format(new_release_dir))

            with cd(new_release_dir):
                # Assume that the user has a deploy key for this repo - this
                # should be created by puppet and manually added to the repo
                sudo('git clone -q --recursive git@github.com:mhl/example-repository.git')

            with cd(new_repo_dir):
                sudo('git checkout {}'.format(committish))
                short_commit = sudo('git rev-parse --short HEAD').strip()

            new_requirements = join(new_repo_dir, 'requirements.txt')
            current_requirements = join(current_repo_dir, 'requirements.txt')
            new_virtualenv_symlink = join(new_release_dir, 'virtualenv')

            if self.requirements_changed(current_requirements, new_requirements):
                # This means that either requirements.txt has changes or that this
                # is the first deploy and current_requirements doesn't exist. In
                # both cases we need to create a new virtualenv.
                new_virtualenv_dir = join(site_root, 'virtualenvs', short_commit)

                sudo("virtualenv --no-site-packages " + new_virtualenv_dir)

                sudo("ln -s {} {}".format(new_virtualenv_dir, new_virtualenv_symlink))
                with virtualenv(new_virtualenv_symlink):
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
                    sudo('./manage.py syncdb --noinput')
                    sudo('./manage.py migrate')

            # FIXME: we actually want to do this in a gunicorn pre_exec hook
            # -f and -n are needed to make sure that it overwrites the existing
            # 'current' symlink:
            sudo("ln -sfn {} {}".format(timestamp, current_release_dir))

        sudo("service example-unicorn restart")

    def requirements_changed(self, current, new):
        diff_command = "diff {} {}".format(current, new)
        diff = sudo(diff_command, warn_only=True)
        return diff.return_code != 0

deploy = DeployTask()
