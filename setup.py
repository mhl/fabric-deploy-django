from setuptools import setup, find_packages
setup(
    name = "fabric-deploy-django",
    version = "0.0.2",
    packages = find_packages(),
    author = "Mark Longair",
    author_email = "mhl@pobox.com",
    description = "A Fabric base class for deploying Django sites",
    license = "MIT",
    keywords = "django fabric deployment",
    install_requires = [
        'Fabric',
        'fabric-virtualenv',
    ]
)
