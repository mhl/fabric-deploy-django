import os

from datetime import datetime
from fabric.api import env, run, settings, sudo, cd


env.use_ssh_config = True

unix_user = 'example'
site_root = '/var/www/example.com'


def host_type():
    run('uname -s')


def deploy(committish):
    with settings(sudo_user=unix_user):
        sudo("ls /var/www")
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
        release_dir = os.path.join(site_root, 'releases', timestamp)
        sudo('mkdir -p {}'.format(release_dir))

        with cd(release_dir):
            # Assume that the user has a deploy key for this repo - this
            # should be created by puppet and manually added to the repo
            sudo('git clone git@github.com:mhl/example-repository.git')
            with cd(os.path.join(release_dir, 'example-repository')):
                sudo('git checkout {}'.format(committish))
