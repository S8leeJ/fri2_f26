lsusb | grep -i microsoft
--------------
t-l

source /opt/ros/humble/setup.bash && python3 -c "import ultralytics, mediapipe, cv_bridge, numpy; print('ok', numpy.__version__)"

cd ~/fri2_f26 && colcon build --symlink-install --packages-select hri_vision

ls ~/bwi_ros2/install | grep azure

mkdir -p ~/bwi_ros2/src && cd ~/bwi_ros2/src && git clone --branch humble https://github.com/microsoft/Azure_Kinect_ROS_Driver.git && cd ~/bwi_ros2 && colcon build --packages-select azure_kinect_ros_driver

------------
t-r

source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 topic list | grep -i image

source ~/bwi_ros2/install/setup.bash && ros2 launch azure_kinect_ros_driver driver.launch.py color_resolution:=720P fps:=15 depth_mode:=NFOV_UNBINNED depth_unit:=16UC1 point_cloud:=false rgb_point_cloud:=false

------------

back to t-l

export ROS_LOCALHOST_ONLY=1 && ros2 topic hz /rgb/image_raw

ros2 topic echo --once /depth_to_rgb/image_raw --field encoding

ros2 run rqt_image_view rqt_image_view

------------

b-l

source /opt/ros/humble/setup.bash && source ~/fri2_f26/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch hri_vision vision_pipeline.launch.py camera_backend:=external rgb_topic:=/rgb/image_raw depth_topic:=/depth_to_rgb/image_raw

-----------

back to t-l (output)

ros2 topic echo /hri/vision/context --field data

-----------

b-r

source /opt/ros/humble/setup.bash && export ROS_LOCALHOST_ONLY=1 && python3 ~/box_viewer.py


ERRORS
----------

lsusb | grep -i -E "045e|microsoft"

dpkg -l | grep -i k4a ; ls /usr/lib/cmake/ | grep -i k4a ; which k4aviewer

ls -d /home/*/bwi_ros2/install/azure_kinect_ros_driver 2>/dev/null