from setuptools import setup, find_packages

setup(
    name="slack_bestof",
    version="0.0.1",
    packages=find_packages(),
    scripts=[],
    entry_points={
        "console_scripts": [
            "slack-bestof=slack_bestof.app:main"
        ],
    },
    install_requires=[
        "slackclient==2.4.0",
        "pymongo==3.10.0"
    ]
)
