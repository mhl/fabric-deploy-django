.. WARNING:::
   We have only used this for personal projects, and can provide
   **no** support, nor any guarantee that it will work
   properly. Also there are a few things in it that are specific
   to our deployments (e.g. installing yuglify with npm,
   force-pushing a ``deployed`` branch if there's certain
   hostname, etc.)

A package containing a Fabric base class for deploying Django
sites.

For example, you can create a fabfile.py like this::

  from fabric_deploy_deploy import DjangoDeployTask

  class ExampleDeployTask(DjangoDeployTask):

      unix_user = 'example'
      site_root = '/var/www/example.com'
      service_name = 'example-unicorn'
      repository_url = 'git@github.com:mhl/example-repository.git'
      repo_dir = 'example-repository'

  deploy = ExampleDeployTask()

When you run that task, e.g. with::

  fab -H remotehost.example.com deploy:master

it will deploy the site under ``/var/www`` with a structure like
the following::

  /var/www
  └── example.com
      ├── logs
      ├── media
      │   └── images
      ├── releases
      │   ├── 2017-01-29T18.27.43
      │   ├── 2017-01-29T18.29.29
      │   ├── 2017-01-29T18.35.35
      │   ├── 2017-01-29T18.46.34
      │   ├── 2017-02-04T16.55.46
      │   ├── 2017-02-04T17.10.53
      │   ├── 2017-02-05T00.47.26
      │   ├── 2017-02-05T18.24.18
      │   └── current -> 2017-02-05T18.24.18
      └── virtualenvs
          ├── a873c33
          ├── ce76a08
          ├── e308ea4
          └── ec49e7a

Each time you deploy, the repository is cloned (starting from
the previous deployment if there is one) into a new timestamped
directory, and if the requirements.txt file has changed, a new
virtualenv is created and packages installed there.

The deployed files will be owned by the user ``unix_user``, so
if the repository specified by ``repository_url`` is a private
GitHub reposotiry then you'll need to generate an SSH key for
that user and add the public key as a deploy key to that
repository on GitHub.

This assumes that you've already created a service to manage
your worker processes, which can be restarted with, for example::

  sudo service example-unicorn restart

if you've set ``service_name`` as above to ``example-unicorn``.

You can deploy different branches, or particular commits, by
specifying them instead of ``master`` when depolying. For
example::

  fab -H remotehost.example.com deploy:new-feature

  fab -H remotehost.example.com deploy:85903ee41b1895

If you need to run migrations with the ``--fake-initial`` you
can do that with, for example::

  fab -H remotehost.example.com deploy:master,fake_initial_migrations=yes
