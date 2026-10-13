#!/usr/bin/env bash
# Start the BWI base without RViz: the Segway driver, the lasers, the map, and AMCL.
# turn_to_person.py needs its /cmd_vel and /odom. fusion_publisher.py starts this.
#
#   bash attention/run_base.sh
#
# Turn on the Segway first. AMCL prints "Please set the initial pose" again and
# again; turning does not use AMCL, so that is not a problem here.

BWI_WS="${BWI_WS:-/home/justin/bwi_ros2}"

[ -f "$BWI_WS/install/setup.bash" ] || {
    echo "❌ FAILED: no BWI build at $BWI_WS."
    exit 1
}

if pgrep -f "segbot_v2\.launch\.py" > /dev/null; then
    echo "❌ FAILED: the BWI base already runs."
    exit 1
fi

source /opt/ros/humble/setup.bash
source "$BWI_WS/install/setup.bash"
export ROS_LOCALHOST_ONLY=1

exec ros2 launch bwi_launch segbot_v2.launch.py gui:=false
