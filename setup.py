from setuptools import setup, find_packages

setup(
    name='qig',
    version='0.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "aioquic",
        "aiocoap",
        "aiomqtt",
        "asyncio-dgram"
    ],
    entry_points={
        'console_scripts': [
            'qig_server=qig.scripts.qig_server:main',
            'qig_client=qig.scripts.qig_client:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.9',
)
