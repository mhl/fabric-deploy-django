from fabric_django_deploy import DjangoDeployTask


class ExampleDeployTask(DjangoDeployTask):

    unix_user = 'example'
    site_root = '/var/www/example.com'
    service_name = 'example-unicorn'
    repository_url = 'git@github.com:mhl/example-repository.git'
    repo_dir = 'example-repository'


deploy = ExampleDeployTask()
