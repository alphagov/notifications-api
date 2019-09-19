#!/bin/bash
#
# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#  http://aws.amazon.com/apache2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

# ELB_LIST defines which Elastic Load Balancers this instance should be part of.
# The elements in ELB_LIST should be seperated by space.
ELB_LIST=""

# Under normal circumstances, you shouldn't need to change anything below this line.
# -----------------------------------------------------------------------------

export PATH="$PATH:/usr/bin:/usr/local/bin"

# If true, all messages will be printed. If false, only fatal errors are printed.
DEBUG=true

# Number of times to check for a resouce to be in the desired state.
WAITER_ATTEMPTS=60

# Number of seconds to wait between attempts for resource to be in a state.
WAITER_INTERVAL=1

# AutoScaling Standby features at minimum require this version to work.
MIN_CLI_VERSION='1.3.25'

# Usage: get_instance_region
#
#   Writes to STDOUT the AWS region as known by the local instance.
get_instance_region() {
    if [ -z "$AWS_REGION" ]; then
        AWS_REGION=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document \
            | grep -i region \
            | awk -F\" '{print $4}')
    fi

    echo $AWS_REGION
}

AWS_CLI="aws --region $(get_instance_region)"


# Usage: get_instance_state_asg <EC2 instance ID>
#
#    Gets the state of the given <EC2 instance ID> as known by the AutoScaling group it's a part of.
#    Health is printed to STDOUT and the function returns 0. Otherwise, no output and return is
#    non-zero.
get_instance_state_asg() {
    local instance_id=$1

    local state=$($AWS_CLI autoscaling describe-auto-scaling-instances \
        --instance-ids $instance_id \
        --query "AutoScalingInstances[?InstanceId == \`$instance_id\`].LifecycleState | [0]" \
        --output text)
    if [ $? != 0 ]; then
        return 1
    else
        echo $state
        return 0
    fi
}

reset_waiter_timeout() {
    local elb=$1
    local state_name=$2

    if [ "$state_name" == "InService" ]; then

        # Wait for a health check to succeed
        local timeout=$($AWS_CLI elb describe-load-balancers \
            --load-balancer-name $elb \
            --query 'LoadBalancerDescriptions[0].HealthCheck.Timeout')

    elif [ "$state_name" == "OutOfService" ]; then

        # If connection draining is enabled, wait for connections to drain
        local draining_values=$($AWS_CLI elb describe-load-balancer-attributes \
            --load-balancer-name $elb \
            --query 'LoadBalancerAttributes.ConnectionDraining.[Enabled,Timeout]' \
            --output text)
        local draining_enabled=$(echo $draining_values | awk '{print $1}')
        local timeout=$(echo $draining_values | awk '{print $2}')

        if [ "$draining_enabled" != "True" ]; then
            timeout=0
        fi

    else
        msg "Unknown state name, '$state_name'";
        return 1;
    fi

    # Base register/deregister action may take up to about 30 seconds
    timeout=$((timeout + 60))

    WAITER_ATTEMPTS=$((timeout / WAITER_INTERVAL))
}

# Usage: wait_for_state <service> <EC2 instance ID> <state name> [ELB name]
#
#    Waits for the state of <EC2 instance ID> to be in <state> as seen by <service>. Returns 0 if
#    it successfully made it to that state; non-zero if not. By default, checks $WAITER_ATTEMPTS
#    times, every $WAITER_INTERVAL seconds. If giving an [ELB name] to check under, these are reset
#    to that ELB's timeout values.
wait_for_state() {
    local service=$1
    local instance_id=$2
    local state_name=$3
    local elb=$4

    local instance_state_cmd
    if [ "$service" == "elb" ]; then
        instance_state_cmd="get_instance_health_elb $instance_id $elb"
        reset_waiter_timeout $elb $state_name
        if [ $? != 0 ]; then
            error_exit "Failed resetting waiter timeout for $elb"
        fi
    elif [ "$service" == "autoscaling" ]; then
        instance_state_cmd="get_instance_state_asg $instance_id"
    else
        msg "Cannot wait for instance state; unknown service type, '$service'"
        return 1
    fi

    msg "Checking $WAITER_ATTEMPTS times, every $WAITER_INTERVAL seconds, for instance $instance_id to be in state $state_name"

    local instance_state=$($instance_state_cmd)
    local count=1

    msg "Instance is currently in state: $instance_state"
    while [ "$instance_state" != "$state_name" ]; do
        if [ $count -ge $WAITER_ATTEMPTS ]; then
            local timeout=$(($WAITER_ATTEMPTS * $WAITER_INTERVAL))
            msg "Instance failed to reach state, $state_name within $timeout seconds"
            return 1
        fi

        sleep $WAITER_INTERVAL

        instance_state=$($instance_state_cmd)
        count=$(($count + 1))
        msg "Instance is currently in state: $instance_state"
    done

    return 0
}

# Usage: get_instance_health_elb <EC2 instance ID> <ELB name>
#
#    Gets the health of the given <EC2 instance ID> as known by <ELB name>. If it's a valid health
#    status (one of InService|OutOfService|Unknown), then the health is printed to STDOUT and the
#    function returns 0. Otherwise, no output and return is non-zero.
get_instance_health_elb() {
    local instance_id=$1
    local elb_name=$2

    msg "Checking status of instance '$instance_id' in load balancer '$elb_name'"

    # If describe-instance-health for this instance returns an error, then it's not part of
    # this ELB. But, if the call was successful let's still double check that the status is
    # valid.
    local instance_status=$($AWS_CLI elb describe-instance-health \
        --load-balancer-name $elb_name \
        --instances $instance_id \
        --query 'InstanceStates[].State' \
        --output text 2>/dev/null)

    if [ $? == 0 ]; then
        case "$instance_status" in
            InService|OutOfService|Unknown)
                echo -n $instance_status
                return 0
                ;;
            *)
                msg "Instance '$instance_id' not part of ELB '$elb_name'"
                return 1
        esac
    fi
}

# Usage: validate_elb <EC2 instance ID> <ELB name>
#
#    Validates that the Elastic Load Balancer with name <ELB name> exists, is describable, and
#    contains <EC2 instance ID> as one of its instances.
#
#    If any of these checks are false, the function returns non-zero.
validate_elb() {
    local instance_id=$1
    local elb_name=$2

    # Get the list of active instances for this LB.
    local elb_instances=$($AWS_CLI elb describe-load-balancers \
        --load-balancer-name $elb_name \
        --query 'LoadBalancerDescriptions[*].Instances[*].InstanceId' \
        --output text)
    if [ $? != 0 ]; then
        msg "Couldn't describe ELB instance named '$elb_name'"
        return 1
    fi

    msg "Checking health of '$instance_id' as known by ELB '$elb_name'"
    local instance_health=$(get_instance_health_elb $instance_id $elb_name)
    if [ $? != 0 ]; then
        return 1
    fi

    return 0
}

# Usage: get_elb_list <EC2 instance ID> <ELB Name>
#
#   Ensures that this instance is related to the named ELB. After execution, the variable
#   "ELB_LIST" will contain the list of load balancers for the given instance.
#
#   If the given instance ID is not found registered to any ELBs, the function returns non-zero
get_elb_list() {
    local instance_id=$1
    local required_elb=$2
    local elb_list=""

    msg "Looking up from ELB list"
    local all_balancers=$($AWS_CLI elb describe-load-balancers \
        --query LoadBalancerDescriptions[*].LoadBalancerName \
        --output text | sed -e $'s/\t/ /g')

    if [[ $all_balancers =~ $required_elb ]]
    then
        local instance_health
        instance_health=$(get_instance_health_elb $instance_id $required_elb)
        if [ $? == 0 ]; then
            elb_list="$elb_list $required_elb"
        fi
    fi

    if [ -z "$elb_list" ]; then
        return 1
    else
        msg "Got load balancer list of: $elb_list"
        ELB_LIST=$elb_list
        return 0
    fi
}

# Usage: deregister_instance <EC2 instance ID> <ELB name>
#
#   Deregisters <EC2 instance ID> from <ELB name>.
deregister_instance() {
    local instance_id=$1
    local elb_name=$2

    $AWS_CLI elb deregister-instances-from-load-balancer \
        --load-balancer-name $elb_name \
        --instances $instance_id 1> /dev/null

    return $?
}

# Usage: register_instance <EC2 instance ID> <ELB name>
#
#   Registers <EC2 instance ID> to <ELB name>.
register_instance() {
    local instance_id=$1
    local elb_name=$2

    $AWS_CLI elb register-instances-with-load-balancer \
        --load-balancer-name $elb_name \
        --instances $instance_id 1> /dev/null

    return $?
}

# Usage: check_cli_version [version-to-check] [desired version]
#
#   Without any arguments, checks that the installed version of the AWS CLI is at least at version
#   $MIN_CLI_VERSION. Returns non-zero if the version is not high enough.
check_cli_version() {
    if [ -z $1 ]; then
        version=$($AWS_CLI --version 2>&1 | cut -f1 -d' ' | cut -f2 -d/)
    else
        version=$1
    fi

    if [ -z "$2" ]; then
        min_version=$MIN_CLI_VERSION
    else
        min_version=$2
    fi

    x=$(echo $version | cut -f1 -d.)
    y=$(echo $version | cut -f2 -d.)
    z=$(echo $version | cut -f3 -d.)

    min_x=$(echo $min_version | cut -f1 -d.)
    min_y=$(echo $min_version | cut -f2 -d.)
    min_z=$(echo $min_version | cut -f3 -d.)

    msg "Checking minimum required CLI version (${min_version}) against installed version ($version)"

    if [ $x -lt $min_x ]; then
        return 1
    elif [ $y -lt $min_y ]; then
        return 1
    elif [ $y -gt $min_y ]; then
        return 0
    elif [ $z -ge $min_z ]; then
        return 0
    else
        return 1
    fi
}

# Usage: msg <message>
#
#   Writes <message> to STDERR only if $DEBUG is true, otherwise has no effect.
msg() {
    local message=$1
    $DEBUG && echo $message 1>&2
}

# Usage: error_exit <message>
#
#   Writes <message> to STDERR as a "fatal" and immediately exits the currently running script.
error_exit() {
    local message=$1

    echo "[FATAL] $message" 1>&2
    exit 1
}

# Usage: get_instance_id
#
#   Writes to STDOUT the EC2 instance ID for the local instance. Returns non-zero if the local
#   instance metadata URL is inaccessible.
get_instance_id() {
    curl -s http://169.254.169.254/latest/meta-data/instance-id
    return $?
}

# Usage: get_instance_name_from_tags <instance_id>
#
# Looks up tags for the given instance, extracting the 'name'
# returns <name> or error_exit
get_instance_name_from_tags() {
    local instance_id=$1

    local instance_name=$($AWS_CLI ec2 describe-tags \
        --filters "Name=resource-id,Values=${instance_id}"  \
        --query Tags[0].Value \
        --output text)
    if [ $? != 0 ]; then
        error_exit "Couldn't get instance name for '$instance_id'"
    fi
    echo $instance_name
    return $?
}

ELB_NAME=""

get_elb_name_for_instance_name() {
    local instance_name=$1

    declare -A elb_to_instance_mapping

    elb_to_instance_mapping['notify-api']='notify-api'
    elb_to_instance_mapping['notify-admin-api']='notify-admin-api'

    elb_to_instance_mapping['notify_api']='notify-api-elb'
    elb_to_instance_mapping['notify_admin_api']='notify-admin-api-elb'

    local elb_name=${elb_to_instance_mapping[${instance_name}]}
    if [ -z $elb_name ]; then
        msg "No ELB for instance ${instance_name}"
    else
        ELB_NAME=$elb_name
    fi
}
