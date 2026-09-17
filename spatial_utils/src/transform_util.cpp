#include <spatial_utils/transform_util.h>

#include <Eigen/Geometry>

/*
    For this one.
        Make a 4x4 Identity matrix using Eigen::MatrixXd::Identity
        Set the right column to the translation, as in the class notes.
        Set the upper-left 3x3 to the rotation matrix.
        You can use Eigen::Quaterniond to turn the quaternion from the
            TransformStamped into a rotation matrix.
            Quaterniond, then .toRotationMatrix
        You can use .block to refer to to the upper-left 3x3 submatrix of your
            4x4 rigid transformation.
*/
Eigen::MatrixXd transformToMatrix(const geometry_msgs::msg::TransformStamped &transform) {
    Eigen::MatrixXd matrix = Eigen::MatrixXd::Identity(4, 4);

    const auto &t = transform.transform.translation;
    matrix(0, 3) = t.x;
    matrix(1, 3) = t.y;
    matrix(2, 3) = t.z;

    const auto &r = transform.transform.rotation;
    Eigen::Quaterniond q(r.w, r.x, r.y, r.z);
    matrix.block<3, 3>(0, 0) = q.toRotationMatrix();

    return matrix;
}

/*
    Converting your 4x4 rigid transformation into a TransformStamped works like
        this.
    Set the header.frame_id to the parent frame,
        and the child_frame_id to the child frame.
    Take the right column as transform.translation.
    Use block to get the 3x3 upper left rotation matrix from the
        rigid transformation.
    Stick that into Eigen::Quaterniond, then pull off the quaternion terms. 
        Put those into the terms of transform.rotation.
    
*/
geometry_msgs::msg::TransformStamped matrixToTransform(
    const Eigen::MatrixXd &matrix, const std::string &parent_frame, const std::string &child_frame) {
    geometry_msgs::msg::TransformStamped transform_msg;
    transform_msg.header.frame_id = parent_frame;
    transform_msg.child_frame_id = child_frame;

    transform_msg.transform.translation.x = matrix(0, 3);
    transform_msg.transform.translation.y = matrix(1, 3);
    transform_msg.transform.translation.z = matrix(2, 3);

    Eigen::Matrix3d rotation = matrix.block<3, 3>(0, 0);
    Eigen::Quaterniond q(rotation);
    transform_msg.transform.rotation.x = q.x();
    transform_msg.transform.rotation.y = q.y();
    transform_msg.transform.rotation.z = q.z();
    transform_msg.transform.rotation.w = q.w();

    return transform_msg;
}

void printTransform(const rclcpp::Logger &logger, geometry_msgs::msg::TransformStamped &transform) {
    RCLCPP_INFO_STREAM(logger,
        "Transform Received:\n" <<
        "  Timestamp: " << transform.header.stamp.sec << "." << transform.header.stamp.nanosec <<

        "  Parent Frame: " << transform.header.frame_id << "\n" <<
        "  Child Frame: " << transform.child_frame_id << "\n" <<
        "  Translation: [" << transform.transform.translation.x << ", "
                           << transform.transform.translation.y << ", "
                           << transform.transform.translation.z << "]\n" <<
        "  Rotation: [" << transform.transform.rotation.x << ", "
                        << transform.transform.rotation.y << ", "
                        << transform.transform.rotation.z << ", "
                        << transform.transform.rotation.w << "]"
    );
}
