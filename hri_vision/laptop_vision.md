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

lsb_release -ds ; find / \( -name "libk4a.so*" -o -iname "k4a*config*.cmake" \) 2>/dev/null | head

source /opt/ros/humble/setup.bash && source /home/justin/bwi_ros2/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 run azure_kinect_ros_driver node --ros-args -p color_enabled:=true -p depth_enabled:=true -p color_resolution:=720P -p fps:=15 -p depth_mode:=NFOV_UNBINNED -p depth_unit:=16UC1 -p point_cloud:=false -p rgb_point_cloud:=false


pip install --user "numpy<2" "opencv-python==4.11.0.86" "opencv-contrib-python==4.11.0.86"

source /opt/ros/humble/setup.bash && python3 -c "import numpy, cv2, cv_bridge, matplotlib.pyplot, mediapipe as mp; print('numpy', numpy.__version__, '| cv2', cv2.__version__, '| solutions', hasattr(mp, 'solutions'))"

----------------

Code
-------------

swathik@flexo:~$ source /opt/ros/humble/setup.bash && source ~/fri2_f26/install/setup.bash && export ROS_LOCALHOST_ONLY=1 && ros2 launch hri_vision vision_pipeline.launch.py camera_backend:=external rgb_topic:=/rgb/image_raw depth_topic:=/depth_to_rgb/image_raw
[INFO] [launch]: All log files can be found below /home/swathik/.ros/log/2026-10-06-17-30-32-598321-flexo-59139
[INFO] [launch]: Default logging verbosity is set to INFO
[INFO] [detection_node-1]: process started with pid [59140]
[INFO] [person_context_node-2]: process started with pid [59142]
[INFO] [orientation_node-3]: process started with pid [59144]
[INFO] [context_builder_node-4]: process started with pid [59146]
[context_builder_node-4] [INFO] [1791325832.981020393] [context_builder_node]: Context builder ready -> /hri/vision/context
[person_context_node-2] [INFO] [1791325833.101509761] [person_context_node]: Person context ready: aligned depth + tracked boxes -> distance/direction/dwell
[orientation_node-3] Downloading model to /home/swathik/.local/lib/python3.10/site-packages/mediapipe/modules/pose_landmark/pose_landmark_lite.tflite
[detection_node-1] [INFO] [1791325834.239244918] [detection_node]: Loading YOLO model: yolo11n.pt
[detection_node-1] [INFO] [1791325834.289900689] [detection_node]: Detection ready: /rgb/image_raw -> /hri/vision/detections; tracker=bytetrack.yaml
[detection_node-1] /home/swathik/.local/lib/python3.10/site-packages/torch/cuda/__init__.py:228: UserWarning: CUDA initialization: CUDA unknown error - this may be due to an incorrectly set up environment, e.g. changing env variable CUDA_VISIBLE_DEVICES after program start. Setting the available devices to be zero. (Triggered internally at /__w/pytorch/pytorch/c10/cuda/CUDAFunctions.cpp:119.)
[detection_node-1]   return torch._C._cuda_getDeviceCount() > 0
[orientation_node-3] WARNING: All log messages before absl::InitializeLog() is called are written to STDERR
[orientation_node-3] I0000 00:00:1791325834.510670   59144 gl_context_egl.cc:85] Successfully initialized EGL. Major : 1 Minor: 5
[orientation_node-3] I0000 00:00:1791325834.513012   59297 gl_context.cc:357] GL version: 3.2 (OpenGL ES 3.2 Mesa 23.2.1-1ubuntu3.1~22.04.4), renderer: Mesa Intel(R) UHD Graphics (CML GT2)
[orientation_node-3] I0000 00:00:1791325834.515987   59144 gl_context_egl.cc:85] Successfully initialized EGL. Major : 1 Minor: 5
[orientation_node-3] I0000 00:00:1791325834.517323   59307 gl_context.cc:357] GL version: 3.2 (OpenGL ES 3.2 Mesa 23.2.1-1ubuntu3.1~22.04.4), renderer: Mesa Intel(R) UHD Graphics (CML GT2)
[orientation_node-3] INFO: Created TensorFlow Lite XNNPACK delegate for CPU.
[orientation_node-3] W0000 00:00:1791325834.519501   59300 inference_feedback_manager.cc:114] Feedback manager requires a model with a single signature inference. Disabling support for feedback tensors.
[orientation_node-3] [INFO] [1791325834.570091354] [orientation_node]: Orientation ready: MediaPipe Pose + Face Detection on tracked person crops
[orientation_node-3] W0000 00:00:1791325834.598585   59282 inference_feedback_manager.cc:114] Feedback manager requires a model with a single signature inference. Disabling support for feedback tensors.
[orientation_node-3] W0000 00:00:1791325834.606907   59274 inference_feedback_manager.cc:114] Feedback manager requires a model with a single signature inference. Disabling support for feedback tensors.
[context_builder_node-4] [INFO] [1791325835.455118507] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":false}}
[context_builder_node-4] [INFO] [1791325836.553008387] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325837.620571978] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325838.684368866] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325839.752157369] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325840.827637870] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325841.897282766] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325842.953124717] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325844.021973417] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325845.088792635] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325846.157171755] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325847.221255800] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325848.289069642] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325849.363863871] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325850.424953546] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325851.492467144] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325852.572146088] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325853.626236669] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.8961573243141174,"distance_m":0.597,"direction":"stationary","dwell_time_s":0.0,"orientation":"unknown","gaze":"unknown","face_visible":null}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[orientation_node-3] /home/swathik/.local/lib/python3.10/site-packages/google/protobuf/symbol_database.py:55: UserWarning: SymbolDatabase.GetPrototype() is deprecated. Please use message_factory.GetMessageClass() instead. SymbolDatabase.GetPrototype() will be removed soon.
[orientation_node-3]   warnings.warn('SymbolDatabase.GetPrototype() is deprecated. Please '
[context_builder_node-4] [INFO] [1791325854.702231460] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.9436541795730591,"distance_m":1.356,"direction":"receding","dwell_time_s":1.07,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325855.769201513] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.9218378067016602,"distance_m":1.826,"direction":"stationary","dwell_time_s":2.14,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325856.839812687] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.9117820262908936,"distance_m":1.859,"direction":"stationary","dwell_time_s":3.21,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325857.897426837] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.9136283993721008,"distance_m":1.862,"direction":"stationary","dwell_time_s":4.27,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325858.969241066] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.8267543315887451,"distance_m":1.699,"direction":"stationary","dwell_time_s":5.34,"orientation":"likely_facing_away","gaze":"unknown","face_visible":false}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325860.036288255] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.8246197700500488,"distance_m":1.726,"direction":"stationary","dwell_time_s":6.41,"orientation":"likely_facing_away","gaze":"unknown","face_visible":false}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325861.104180902] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.868252158164978,"distance_m":1.753,"direction":"stationary","dwell_time_s":7.48,"orientation":"sideways","gaze":"unknown","face_visible":false}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325862.173808943] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.9180128574371338,"distance_m":1.896,"direction":"stationary","dwell_time_s":8.55,"orientation":"unknown","gaze":"unknown","face_visible":false}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325863.244414937] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.8841676712036133,"distance_m":1.773,"direction":"stationary","dwell_time_s":9.62,"orientation":"sideways","gaze":"unknown","face_visible":false}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325864.304430529] [context_builder_node]: {"person_count":1,"people":[{"id":1,"confidence":0.8695656657218933,"distance_m":0.96,"direction":"approaching","dwell_time_s":10.68,"orientation":"facing_robot","gaze":"toward_robot","face_visible":true}],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325865.367425966] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325866.435413293] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325867.513182982] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325868.578367776] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325869.636058228] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325870.713863103] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
[context_builder_node-4] [INFO] [1791325871.780524504] [context_builder_node]: {"person_count":0,"people":[],"sensor_status":{"depth_fresh":true,"orientation_fresh":true}}
^C[WARNING] [launch]: user interrupted with ctrl-c (SIGINT)
[detection_node-1] Traceback (most recent call last):
[detection_node-1]   File "/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/detection_node", line 33, in <module>
[detection_node-1]     sys.exit(load_entry_point('hri-vision', 'console_scripts', 'detection_node')())
[detection_node-1]   File "/home/swathik/fri2_f26/build/hri_vision/hri_vision/detection_node.py", line 124, in main
[detection_node-1]     rclpy.shutdown()
[detection_node-1]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/__init__.py", line 130, in shutdown
[detection_node-1]     _shutdown(context=context)
[detection_node-1]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/utilities.py", line 58, in shutdown
[detection_node-1]     return context.shutdown()
[detection_node-1]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/context.py", line 102, in shutdown
[detection_node-1]     self.__context.shutdown()
[detection_node-1] rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called on the given context, at ./src/rcl/init.c:241
[context_builder_node-4] Traceback (most recent call last):
[context_builder_node-4]   File "/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/context_builder_node", line 33, in <module>
[context_builder_node-4]     sys.exit(load_entry_point('hri-vision', 'console_scripts', 'context_builder_node')())
[context_builder_node-4]   File "/home/swathik/fri2_f26/build/hri_vision/hri_vision/context_builder_node.py", line 121, in main
[context_builder_node-4]     rclpy.shutdown()
[context_builder_node-4]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/__init__.py", line 130, in shutdown
[context_builder_node-4]     _shutdown(context=context)
[context_builder_node-4]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/utilities.py", line 58, in shutdown
[context_builder_node-4]     return context.shutdown()
[context_builder_node-4]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/context.py", line 102, in shutdown
[context_builder_node-4]     self.__context.shutdown()
[context_builder_node-4] rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called on the given context, at ./src/rcl/init.c:241
[person_context_node-2] Traceback (most recent call last):
[person_context_node-2]   File "/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/person_context_node", line 33, in <module>
[person_context_node-2]     sys.exit(load_entry_point('hri-vision', 'console_scripts', 'person_context_node')())
[person_context_node-2]   File "/home/swathik/fri2_f26/build/hri_vision/hri_vision/person_context_node.py", line 194, in main
[person_context_node-2]     rclpy.shutdown()
[person_context_node-2]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/__init__.py", line 130, in shutdown
[person_context_node-2]     _shutdown(context=context)
[person_context_node-2]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/utilities.py", line 58, in shutdown
[person_context_node-2]     return context.shutdown()
[person_context_node-2]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/context.py", line 102, in shutdown
[person_context_node-2]     self.__context.shutdown()
[person_context_node-2] rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called on the given context, at ./src/rcl/init.c:241
[orientation_node-3] Traceback (most recent call last):
[orientation_node-3]   File "/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/orientation_node", line 33, in <module>
[orientation_node-3]     sys.exit(load_entry_point('hri-vision', 'console_scripts', 'orientation_node')())
[orientation_node-3]   File "/home/swathik/fri2_f26/build/hri_vision/hri_vision/orientation_node.py", line 221, in main
[orientation_node-3]     rclpy.shutdown()
[orientation_node-3]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/__init__.py", line 130, in shutdown
[orientation_node-3]     _shutdown(context=context)
[orientation_node-3]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/utilities.py", line 58, in shutdown
[orientation_node-3]     return context.shutdown()
[orientation_node-3]   File "/opt/ros/humble/local/lib/python3.10/dist-packages/rclpy/context.py", line 102, in shutdown
[orientation_node-3]     self.__context.shutdown()
[orientation_node-3] rclpy._rclpy_pybind11.RCLError: failed to shutdown: rcl_shutdown already called on the given context, at ./src/rcl/init.c:241
[ERROR] [context_builder_node-4]: process has died [pid 59146, exit code 1, cmd '/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/context_builder_node --ros-args -r __node:=context_builder_node --params-file /home/swathik/fri2_f26/install/hri_vision/share/hri_vision/config/vision.yaml'].
[ERROR] [person_context_node-2]: process has died [pid 59142, exit code 1, cmd '/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/person_context_node --ros-args -r __node:=person_context_node --params-file /home/swathik/fri2_f26/install/hri_vision/share/hri_vision/config/vision.yaml --params-file /tmp/launch_params_uub4dyv9'].
[ERROR] [orientation_node-3]: process has died [pid 59144, exit code 1, cmd '/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/orientation_node --ros-args -r __node:=orientation_node --params-file /home/swathik/fri2_f26/install/hri_vision/share/hri_vision/config/vision.yaml --params-file /tmp/launch_params_qe3glqlo'].
[ERROR] [detection_node-1]: process has died [pid 59140, exit code 1, cmd '/home/swathik/fri2_f26/install/hri_vision/lib/hri_vision/detection_node --ros-args -r __node:=detection_node --params-file /home/swathik/fri2_f26/install/hri_vision/share/hri_vision/config/vision.yaml --params-file /tmp/launch_params_8fug4ar3'].
swathik@flexo:~$ 
