import os

from datetime import datetime
from fabric.api import env, run, settings, sudo, cd
from fabvenv import virtualenv


env.sudo_prefix += '-H '
env.use_ssh_config = True

unix_user = 'example'
site_root = '/var/www/example.com'


def host_type():
    run('uname -s')


def deploy(committish):
    with settings(sudo_user=unix_user):
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
        timestamp = timestamp.replace(':', '.')

        new_release_dir = os.path.join(site_root, 'releases', timestamp)
        new_repo_dir = os.path.join(new_release_dir, 'example-repository')
        current_release_dir = os.path.join(site_root, 'releases', 'current')
        current_repo_dir = os.path.join(current_release_dir, 'example-repository')
        sudo('mkdir -p {}'.format(new_release_dir))

        with cd(new_release_dir):
            # Assume that the user has a deploy key for this repo - this
            # should be created by puppet and manually added to the repo
            sudo('git clone -q git@github.com:mhl/example-repository.git')

        with cd(new_repo_dir):
            sudo('git checkout {}'.format(committish))
            short_commit = sudo('git rev-parse --short HEAD').strip()

        new_requirements = os.path.join(new_repo_dir, 'requirements.txt')
        current_requirements = os.path.join(current_repo_dir, 'requirements.txt')
        new_virtualenv_symlink = os.path.join(new_release_dir, 'virtualenv')

        diff_command = "diff {} {}"
        diff = sudo(diff_command.format(current_requirements, new_requirements),
                    warn_only=True)
        if diff.return_code == 0:
            # requirements.txt for the new release is the same as for the
            # current one, so we can re-use its virtualenv.
            current_virtualenv = sudo("readlink -n -f " + os.path.join(current_release_dir, 'virtualenv'))
            sudo("ln -s {} {}".format(current_virtualenv, new_virtualenv_symlink))
        else:
            # This means that either requirements.txt has changes or that this
            # is the first deploy and current_requirements doesn't exist. In
            # both cases we need to create a new virtualenv.
            new_virtualenv_dir = os.path.join(site_root, 'virtualenvs', short_commit)

            sudo("virtualenv --no-site-packages " + new_virtualenv_dir)

            sudo("ln -s {} {}".format(new_virtualenv_dir, new_virtualenv_symlink))
            with virtualenv(new_virtualenv_symlink):
                sudo('pip install -q -r ' + new_requirements)
            with cd(new_virtualenv_symlink):
                sudo('npm install yuglify')

        with virtualenv(new_virtualenv_symlink):
            with cd(new_repo_dir):
                # TODO: Should we be doing something special with settings at
                # this point?
                yuglify_bin_dir = os.path.join(new_virtualenv_symlink, 'node_modules', 'yuglify', 'bin')
                sudo('export PATH="{}:$PATH" && ./manage.py collectstatic --noinput'.format(yuglify_bin_dir))
                sudo('./manage.py syncdb --noinput')
                sudo('./manage.py migrate')
