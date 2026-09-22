from setuptools import find_packages, setup

package_name = "audio_context"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test", "tools"]),
    data_files=[
        # The marker that lets `ros2 run audio_context ...` find this package
        # by name. The file is empty; only its name matters.
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Mayank Konduri",
    maintainer_email="mayank@example.com",
    description="Audio context for conversation initiation.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            # ros2 run audio_context node
            "node = audio_context.node:main",
        ],
    },
)