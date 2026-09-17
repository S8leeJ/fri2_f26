#include "follower_robot/MoveToTarget.h"

#include <Eigen/Geometry>
#include <geometry_msgs/msg/pose_stamped.hpp>

//I have implemented the entire constructor for you.
MoveToTarget::MoveToTarget(rclcpp::Node *node) :
    node_(node),
    send_goal_options_(rclcpp_action::Client<nav2_msgs::action::NavigateToPose>::SendGoalOptions()) {
    client_ = rclcpp_action::create_client<nav2_msgs::action::NavigateToPose>(node, "navigate_to_pose");

    while (!client_->wait_for_action_server(std::chrono::seconds(5))) {
        RCLCPP_INFO(node_->get_logger(), "Waiting for Nav2 action server...");
    }

    // send_goal_options.goal_response_callback = goal_response_callback;
    send_goal_options_.goal_response_callback =
        std::bind(&MoveToTarget::goal_response_callback, this,
            std::placeholders::_1);
    send_goal_options_.result_callback =
        std::bind(&MoveToTarget::result_callback, this,
            std::placeholders::_1);
}

MoveToTarget::~MoveToTarget() {}

/*
    I set the goal response and result callbacks for you. You don't really
        need them, but you may want to use them to print some I/O during
        operation for debugging. I figured you wouldn't need the feedback
        callback, so I didn't implement it.
*/
void MoveToTarget::goal_response_callback(
    std::shared_ptr<rclcpp_action::ClientGoalHandle<nav2_msgs::action::NavigateToPose>> goal_handle) {
    if (!goal_handle) {
        RCLCPP_ERROR(node_->get_logger(), "Goal was rejected!");
    } else {
        RCLCPP_INFO(node_->get_logger(), "Goal accepted!");
    }
}    

void MoveToTarget::result_callback(
    const rclcpp_action::ClientGoalHandle<nav2_msgs::action::NavigateToPose>::WrappedResult &result) {
}

/*
    You want to send the navigation goal as a
        nav2_msgs::action::NavigateToPose::Goal, expressed relative to
        base_link.
    Step one. Fill in the PoseStamped.
    You can get the quaternion terms for the orientation using
        Eigen::Quaterniond
    The translational terms you can pull out of the right column of the input
        4x4 rigid transformation matrix.
    Set goal_pose.header.stamp. 
    Stuff the goal_pose into the goal_msg. 
    Call client_->async_send_goal to send it along.
*/
void MoveToTarget::copyToGoalPoseAndSend(
    Eigen::MatrixXd &goal_pose_relative_to_base_link
    ) {
    RCLCPP_INFO(node_->get_logger(), "Sending goal!");
    geometry_msgs::msg::PoseStamped goal_pose;
    goal_pose.header.frame_id = "base_link";
    goal_pose.header.stamp = node_->get_clock()->now();
    goal_pose.pose.position.x = goal_pose_relative_to_base_link(0, 3);
    goal_pose.pose.position.y = goal_pose_relative_to_base_link(1, 3);
    goal_pose.pose.position.z = goal_pose_relative_to_base_link(2, 3);

    Eigen::Matrix3d rotation = goal_pose_relative_to_base_link.block<3, 3>(0, 0);
    Eigen::Quaterniond q(rotation);
    goal_pose.pose.orientation.x = q.x();
    goal_pose.pose.orientation.y = q.y();
    goal_pose.pose.orientation.z = q.z();
    goal_pose.pose.orientation.w = q.w();

    nav2_msgs::action::NavigateToPose::Goal goal_msg = nav2_msgs::action::NavigateToPose::Goal();
    goal_msg.pose = goal_pose;
    client_->async_send_goal(goal_msg, send_goal_options_);
}