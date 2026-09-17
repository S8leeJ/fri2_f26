#include "follower_robot/FollowerRobotNode.h"
#include <spatial_utils/transform_util.h>

#include <Eigen/Core>
#include <Eigen/Geometry>
#include <tf2/exceptions.h>
#include <tf2/time.h>

#include <cmath>

using namespace std;

/*
    I have initialized all of the class attributes for you.
    You shouldn't need anything else in the constructor.
*/
FollowerRobotNode::FollowerRobotNode(
    double follow_distance,
    double tag_motion_threshold):
    Node("follower_robot_node"),
    follow_distance_(follow_distance),
    tag_motion_threshold_(tag_motion_threshold),
    move_to_target_(this),
    tf_buffer_(this->get_clock()),
    tf_listener_(tf_buffer_),
    tf_broadcaster_(this),
    m_map_to_tag_1_prev_(Eigen::Matrix4d::Identity()),
    m_map_to_go_to_(Eigen::Matrix4d::Identity())
{
    previous_stamp_ = rclcpp::Time(0, 0, this->get_clock()->get_clock_type());
    april_tag_sub_ = this->create_subscription<apriltag_msgs::msg::AprilTagDetectionArray>(
        "/apriltag_detections", 1,
        std::bind(&FollowerRobotNode::aprilTagCallback, this, std::placeholders::_1)
    );
}

FollowerRobotNode::~FollowerRobotNode() {}

/*
    I have provided this implementation. You really shouldn't need to change
        it.
*/
void FollowerRobotNode::aprilTagCallback(const apriltag_msgs::msg::AprilTagDetectionArray::SharedPtr msg) {
    // RCLCPP_INFO_STREAM(this->get_logger(), "aprilTagCallback");
    for (size_t i = 0; i < msg->detections.size(); ++i) {
        const apriltag_msgs::msg::AprilTagDetection &detection = msg->detections[i];
        if (detection.id == 1) {
            //Found Tag ID 1
            //Unsure that the robot sees the tag? Uncomment this line.
            // RCLCPP_INFO_STREAM(this->get_logger(), "FOUND TAG ID 1");

            /*
                The tag is the one on the clipboard.
                It is tag ID 1 from family tag25h9 in April Tag, 200mm.
                If you run into problems, get a peer mentor who knows how to
                print another to print another.
                OR YOU CAN DO IT!
                https://chaitanyantr.github.io/apriltag.html

                Note that only tag 1 will work...
                    unless you change detection to be another number.
                    And print another tag.
                    Go wild!
            */

            //You will implement computeAndAct();
            computeAndAct();
        }
    }
}

/*
You are responsible for implementing this.
Note that you should use Eigen for your matrix computations.
When the robot is done moving, it should be follow_distance away from the
    target, and facing the target. 
That is not to say "facing the same direction as the target."
The robot should be pointing to the x,y position of the target, from
the position it ends in.

*/
Eigen::MatrixXd FollowerRobotNode::computeGoToFrameFromBaseLink(
    geometry_msgs::msg::TransformStamped &base_link_to_tag1) {
    /*
        How do you implement this?

        You can find how to make a 4x4 Rigid Transformation in the class notes.
        The class should return a 4x4 Rigid Transformation.

        Think of the position of the tag as an x, y problem in 2D.
        You cannot tilt the robot up and down to deal with Z.

        So.. 
        You can get x, and y from the tag's translation. 
        You can find the angle that it should rotate about the z axis using
            atan2
        You can compute the rotation matrix to face in that direction using
            Eigen::AngleAxisd
        You can turn an Eigen::AngleAxisd into a rotation matrix using
            .toRotationMatrix.

        You can create a 4x4 Eigen matrix using the
            Eigen::MatrixXd::Identity function. 
        You can write the upper left-hand 3x3 using the block command.

        You can figure out which direction the robot should be pointing in
            by considering x and y of the tag, since the tag is expressed
            relative to the camera (and thus relative to the base.. 
            for this exercise, you can pretend that they're in the same place
            the solution works out the same). 

        Okay, so the robot should go to a spot that is follow_distance closer
            than x,y of the tag.

        Stuff the translational components into your 4x4 rigid transform.

        That's a lot of help! Go write this thing!!
    */
    Eigen::MatrixXd transform = Eigen::MatrixXd::Identity(4, 4);

    const double x = base_link_to_tag1.transform.translation.x;
    const double y = base_link_to_tag1.transform.translation.y;
    const double distance = std::hypot(x, y);
    if (distance < 1e-6) {
        return transform;
    }

    const double yaw = std::atan2(y, x);
    const Eigen::Matrix3d rotation =
        Eigen::AngleAxisd(yaw, Eigen::Vector3d::UnitZ()).toRotationMatrix();
    transform.block<3, 3>(0, 0) = rotation;

    const double go_distance = distance - follow_distance_;
    transform(0, 3) = (x / distance) * go_distance;
    transform(1, 3) = (y / distance) * go_distance;
    transform(2, 3) = 0.0;

    return transform;
}

//You implement this as part of the homework.
double FollowerRobotNode::computeDistanceBaseLinkTag1(
    geometry_msgs::msg::TransformStamped &base_link_to_tag1) {
    /*
        The camera is at the origin and the tag's translaton is relative to
        the position of the camera.

        Distance is just l2 norm or Euclidean distance. You've got this.
    */
    const auto &t = base_link_to_tag1.transform.translation;
    double distance = std::sqrt(t.x * t.x + t.y * t.y + t.z * t.z);
    RCLCPP_INFO_STREAM(this->get_logger(),
        "distance:  " << distance << endl);
    return distance;  
}

//I implemented this. You do not need to change it.
bool FollowerRobotNode::theTagMoved(
    geometry_msgs::msg::TransformStamped &map_to_base_link,
    geometry_msgs::msg::TransformStamped &base_link_to_tag1
    ) {
        bool tagMotionConfirmed = false;
        rclcpp::Time map_to_base_stamp =
            rclcpp::Time(map_to_base_link.header.stamp);
        rclcpp::Time base_to_tag_stamp =
            rclcpp::Time(base_link_to_tag1.header.stamp);
        rclcpp::Time composed_stamp =
            map_to_base_stamp < base_to_tag_stamp ?
                map_to_base_stamp : base_to_tag_stamp;

        if(composed_stamp > previous_stamp_) {
            previous_stamp_ = composed_stamp;

            Eigen::MatrixXd m_map_to_base_link =
                transformToMatrix(map_to_base_link);
            Eigen::MatrixXd m_base_link_to_tag_1 =
                transformToMatrix(base_link_to_tag1);
            Eigen::MatrixXd m_map_to_tag_1 = m_map_to_base_link * m_base_link_to_tag_1;

            double tag_motion = 
                (m_map_to_tag_1.block<3,1>(0,3) - 
                m_map_to_tag_1_prev_.block<3,1>(0,3)).norm();

            // RCLCPP_INFO_STREAM(this->get_logger(), "THE TAG MOVED:  " << tag_motion << endl);
            tagMotionConfirmed = tag_motion > tag_motion_threshold_;
            if(tagMotionConfirmed) m_map_to_tag_1_prev_ = m_map_to_tag_1;
        }
    return tagMotionConfirmed;
}

/*
    You implement this.
    Here's a rough outline:
        You're going to look up map_to_base_link and base_link_to_tag1.
        You use tf_buffer_.lookupTransform in each case. 

        If the tag has moved (determined by theTagMoved, which I implemented):
        AND if the tag is farther than follow_distance_ away:
            Compute m_map_to_base_link using transformToMatrix(map_to_base_link);
            Compute m_go_to using computeGoToFromBaseLink(base_link_to_tag1);
            Both of these are provided, since you implement both functions.
            Compute m_map_to_go_to_ as the pose you want the robot to go, but
                expressed relative to the map frame. 
            Call move_to_target.copyToGoalPoseAndSend. This should use the 4x4
                rigid transformation expressed relative to base_link, which is
                the result of computeGoToFrameFromBaseLink.
        Even if the tag has not moved (outside of the if). Broadcast
            m_map_to_go_to as a transform relative to the map frame.
        Use geometry_msgs::msg::TransformStamped, set tf1.header.stamp, and use
            tf_broadcaster_.sendTransform.
*/
void FollowerRobotNode::computeAndAct() {
    try{
        geometry_msgs::msg::TransformStamped map_to_base_link =
            tf_buffer_.lookupTransform("map", "base_link", tf2::TimePointZero);
        geometry_msgs::msg::TransformStamped base_link_to_tag1 =
            tf_buffer_.lookupTransform("base_link", "tag1", tf2::TimePointZero);
        if(theTagMoved(map_to_base_link, base_link_to_tag1)) {
            RCLCPP_INFO_STREAM(this->get_logger(), "THE TAG MOVED" << endl);
            double distance = computeDistanceBaseLinkTag1(base_link_to_tag1);
            if(distance > follow_distance_) {
                Eigen::MatrixXd m_map_to_base_link =
                    transformToMatrix(map_to_base_link);
                Eigen::MatrixXd m_go_to =
                    computeGoToFrameFromBaseLink(base_link_to_tag1);
                /*
                    Compute m_map_to_go_to_ here. This updates the go to for
                        the entire class, assuring that you always broadcast
                        the correct pose.
                */
                m_map_to_go_to_ = m_map_to_base_link * m_go_to;

                move_to_target_.copyToGoalPoseAndSend(m_go_to);
            }
        }
        /*
            Fill in the TransformStamped using matrixToTransform.
            Set tf1.header.stamp.
            Send using tf_broadcaster_.
        */
        geometry_msgs::msg::TransformStamped tf1 =
            matrixToTransform(m_map_to_go_to_, "map", "go_to");
        tf1.header.stamp = this->get_clock()->now();
        tf_broadcaster_.sendTransform(tf1);

    } catch (const tf2::TransformException &ex) {
        RCLCPP_WARN(this->get_logger(), "Could not transform world -> example_frame: %s", ex.what());
    }
}