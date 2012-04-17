#!/usr/bin/python

import roslib
roslib.load_manifest('srs_states')
import rospy
import smach
import smach_ros

import copy

from simple_script_server import *
sss = simple_script_server()

import tf
from tf.transformations import *
from kinematics_msgs.srv import *

#this should be in manipulation_msgs
from cob_mmcontroller.msg import *

from shared_state_information import *
#import grasping_functions



## Select grasp state
#
# This state select a grasping strategy. A high object will be grasped from the side, a low one from top.
class select_grasp(smach.State):

    def __init__(self):
        smach.State.__init__(
            self,
            outcomes=['succeeded', 'failed', 'preempted'],
            input_keys=['object'],
            output_keys=['grasp_categorisation'])
        
        """
        Very simple grasp selection
        This need to be transfered into symbolic grounding service
        """
        self.height_switch = 0.5 # Switch to select top or side grasp using the height of the object over the ground in [m].
        
        #self.listener = tf.TransformListener()
        
        #default grasp categorisation
        self.grasp_categorisation = 'side'

    def execute(self, userdata):
        
        global listener
        try:
            # transform object_pose into base_link
            object_pose_in = userdata.object.pose
            print object_pose_in
            object_pose_in.header.stamp = listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
            object_pose_bl = listener.transformPose("/base_link", object_pose_in)
        except rospy.ROSException, e:
            print "Transformation not possible: %s"%e
            return 'failed'
        
        if object_pose_bl.pose.position.z >= self.height_switch: #TODO how to select grasps for objects within a cabinet or shelf?
            userdata.grasp_categorisation='side'
        else: 
            userdata.grasp_categorisation= 'top'
        
        if self.preempt_requested():
            self.service_preempt()
            return 'preempted'
        
        return 'succeeded'


## Grasp general state
#
# This state will grasp an object with a side grasp
class grasp_simple(smach.State):

    def __init__(self, max_retries = 1):
        smach.State.__init__(
            self,
            outcomes=['succeeded', 'retry', 'no_more_retries', 'failed', 'preempted'],
            input_keys=['object','grasp_categorisation'])
        
        self.max_retries = max_retries
        self.retries = 0
        self.iks = rospy.ServiceProxy('/arm_kinematics/get_ik', GetPositionIK)
        #self.listener = tf.TransformListener()
        self.stiffness = rospy.ServiceProxy('/arm_controller/set_joint_stiffness', SetJointStiffness)


    def callIKSolver(self, current_pose, goal_pose):
        req = GetPositionIKRequest()
        req.ik_request.ik_link_name = "sdh_grasp_link"
        req.ik_request.ik_seed_state.joint_state.position = current_pose
        req.ik_request.pose_stamped = goal_pose
        resp = self.iks(req)
        result = []
        for o in resp.solution.joint_state.position:
            result.append(o)
        return (result, resp.error_code)

    def execute(self, userdata):
        global current_task_info
        
        if not current_task_info.object_in_hand: #no object in hand

            if self.preempt_requested():
                self.service_preempt()
                return 'preempted'
            
            global listener
            # check if maximum retries reached
            if self.retries > self.max_retries:
                self.retries = 0
                return 'no_more_retries'
            
            # transform object_pose into base_link
            object_pose_in = userdata.object.pose
            object_pose_in.header.stamp = listener.getLatestCommonTime("/base_link",object_pose_in.header.frame_id)
            object_pose_bl = listener.transformPose("/base_link", object_pose_in)
            
            
            if userdata.grasp_categorisation == 'side':
                # make arm soft TODO: handle stiffness for schunk arm
                try:
                    self.stiffness([300,300,300,100,100,100,100])
                except rospy.ServiceException, e:
                    print "Service call failed: %s"%e
                    self.retries = 0
                    return 'failed'
            
                [new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(-1.552, -0.042, 2.481) # rpy 
                object_pose_bl.pose.orientation.x = new_x
                object_pose_bl.pose.orientation.y = new_y
                object_pose_bl.pose.orientation.z = new_z
                object_pose_bl.pose.orientation.w = new_w
        
                # FIXME: this is calibration between camera and hand and should be removed from scripting level
                object_pose_bl.pose.position.x = object_pose_bl.pose.position.x #- 0.06 #- 0.08
                object_pose_bl.pose.position.y = object_pose_bl.pose.position.y #- 0.05
                object_pose_bl.pose.position.z = object_pose_bl.pose.position.z  #- 0.1
                
                # calculate pre and post grasp positions
                pre_grasp_bl = PoseStamped()
                post_grasp_bl = PoseStamped()
                pre_grasp_bl = copy.deepcopy(object_pose_bl)
                post_grasp_bl = copy.deepcopy(object_pose_bl)
        
                #pre_grasp_bl.pose.position.x = pre_grasp_bl.pose.position.x + 0.10 # x offset for pre grasp position
                #pre_grasp_bl.pose.position.y = pre_grasp_bl.pose.position.y + 0.10 # y offset for pre grasp position
                #post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
                #post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.15 # z offset for post grasp position
        
                pre_grasp_bl.pose.position.x = pre_grasp_bl.pose.position.x + 0.10 # x offset for pre grasp position
                pre_grasp_bl.pose.position.y = pre_grasp_bl.pose.position.y + 0.10 # y offset for pre grasp position
                pre_grasp_bl.pose.position.z = pre_grasp_bl.pose.position.z + 0.15 # y offset for pre grasp position
                post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
                post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.17 # z offset for post grasp position
                
            elif userdata.grasp_categorisation == 'top':
                try:
                    self.stiffness([100,100,100,100,100,100,100])
                except rospy.ServiceException, e:
                    print "Service call failed: %s"%e
                    self.retries = 0
                    return 'failed'
            
                # use a predefined (fixed) orientation for object_pose_bl
                [new_x, new_y, new_z, new_w] = tf.transformations.quaternion_from_euler(3.121, 0.077, -2.662) # rpy 
                object_pose_bl.pose.orientation.x = new_x
                object_pose_bl.pose.orientation.y = new_y
                object_pose_bl.pose.orientation.z = new_z
                object_pose_bl.pose.orientation.w = new_w
        
                # FIXME: this is calibration between camera and hand and should be removed from scripting level
                object_pose_bl.pose.position.x = object_pose_bl.pose.position.x #-0.04 #- 0.08
                object_pose_bl.pose.position.y = object_pose_bl.pose.position.y# + 0.02
                object_pose_bl.pose.position.z = object_pose_bl.pose.position.z #+ 0.07
        
                # calculate pre and post grasp positions
                pre_grasp_bl = PoseStamped()
                post_grasp_bl = PoseStamped()
                pre_grasp_bl = copy.deepcopy(object_pose_bl)
                post_grasp_bl = copy.deepcopy(object_pose_bl)
            
                pre_grasp_bl.pose.position.z = pre_grasp_bl.pose.position.z + 0.18 # z offset for pre grasp position
                post_grasp_bl.pose.position.x = post_grasp_bl.pose.position.x + 0.05 # x offset for post grasp position
                post_grasp_bl.pose.position.z = post_grasp_bl.pose.position.z + 0.15 # z offset for post grasp position
            else:
                return 'failed'
                #unknown categorisation
               
                
    
            # calculate ik solutions for pre grasp configuration
            arm_pre_grasp = rospy.get_param("/script_server/arm/pregrasp_top")
            (pre_grasp_conf, error_code) = self.callIKSolver(arm_pre_grasp[0], pre_grasp_bl)        
            if(error_code.val != error_code.SUCCESS):
                rospy.logerr("Ik pre_grasp Failed")
                self.retries += 1
                return 'retry'
            
            # calculate ik solutions for grasp configuration
            (grasp_conf, error_code) = self.callIKSolver(pre_grasp_conf, object_pose_bl)
            if(error_code.val != error_code.SUCCESS):
                rospy.logerr("Ik grasp Failed")
                self.retries += 1
                return 'retry'
            
            # calculate ik solutions for pre grasp configuration
            (post_grasp_conf, error_code) = self.callIKSolver(grasp_conf, post_grasp_bl)
            if(error_code.val != error_code.SUCCESS):
                rospy.logerr("Ik post_grasp Failed")
                self.retries += 1
                return 'retry'    
        
            # execute grasp
            if self.preempt_requested():
                self.service_preempt()
                return 'preempted'
            
            sss.say(["I am grasping the " + userdata.object.label + " now."],False)
            sss.move("torso","home")
            handle_arm = sss.move("arm", [pre_grasp_conf , grasp_conf],False)
            
            if userdata.grasp_categorisation == 'side':
                sss.move("sdh", "cylopen")
            elif userdata.grasp_categorisation == 'top':
                sss.move("sdh", "spheropen")
            else:
                return 'failed'
            
            if self.preempt_requested():
                self.service_preempt()
                handle_arm.client.cancel_goal()
                return 'preempted'
            else:
                handle_arm.wait()
                
                
            if self.preempt_requested():
                self.service_preempt()
                return 'preempted'
            else:
                if userdata.grasp_categorisation == 'side':
                    sss.move("sdh", "cylclosed")
                elif userdata.grasp_categorisation == 'top':
                    sss.move("sdh", "spherclosed")
                else:
                    return 'failed'
                    #unknown categorisation
                    
                #object is already in hand    
                current_task_info.object_in_hand = True
                #object graspped, any previous detection is not valid anymore
                current_task_info.set_object_identification_state(False) 
                #New object grasp, post grasp adjustment might be required
                current_task_info.set_post_grasp_adjustment_state(False)  
            
        sss.move("arm", [post_grasp_conf, "hold"])
        self.retries = 0     
        return 'succeeded'


## Grasp general state
#
# This state will grasp an object with a side grasp configuration coming from the grasp planner
class grasp(smach.State):

    def __init__(self):
        smach.State.__init__(
            self,
            outcomes=['succeeded', 'failed', 'preempted'],
            input_keys=['hand_grasp_configuration', 'arm_pre_grasp_position', 'arm_grasp_position'])

    def poseStampedtoSSS(self,pose_stamped):
        pose = pose_stamped.pose
        euler = euler_from_quaternion(pose.orientation.x,pose.orientation.y,pose.orientation.z,pose.orientation.w)
        return [[pose_stamped.frame_id, [pose.position.x,pose.position.y,pose.position.z],list(euler)]]
        
    def execute(self, userdata):
      config_sdh = [userdata.hand_grasp_configuration]
      config_pregrasp = self.poseStampedToSSS(userdata.arm_pre_grasp_position)
      config_grasp = self.poseStampedToSSS(userdata.arm_grasp_position)
      
      #1. call IK Solver for pre-grasp
      ik_pregrasp, error_pregrasp = sss.calculate_ik(config_pregrasp)
      if error_pregrasp is not error_pregrasp.SUCCESS:
          return 'failed'    
          
      #5. call IK Solver for grasp
      ik_grasp, error_grasp = sss.calculate_ik(config_grasp)
      if error_grasp is not error_grasp.SUCCESS:
          return 'failed'    
      
      #2. call arm planner for pre-grasp
      #3. move arm to pre-grasp
      sss.move_planned('arm',ik_pregrasp)
      
      #4. open gripper
      sss.move('sdh','cylopen')
      
      #6. move arm to grasp (re-planning probably not necessary)
      
      #TODO: use interpolated ik planner
      sss.move('arm',ik_pregrasp)
      
      #7. close gripper
      sss.move('sdh',config_sdh)
      #8. check if grasp successful
      successful_grasp = grasping_functions.sdh_tactil_sensor_result();
      
      if successful_grasp:
         return 'succeeded'
      else:
         #TODO: open hand, go back to pregrasp to be safe ? 
         return 'failed'