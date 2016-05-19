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

. $(dirname $0)/common_functions.sh

msg "Running AWS CLI with region: $(get_instance_region)"

# get this instance's ID
INSTANCE_ID=$(get_instance_id)
if [ $? != 0 -o -z "$INSTANCE_ID" ]; then
    error_exit "Unable to get this instance's ID; cannot continue."
fi

# Get current time
msg "Started $(basename $0) at $(/bin/date "+%F %T")"
start_sec=$(/bin/date +%s.%N)

msg "Getting relevant load balancer"
INSTANCE_NAME=$(get_instance_name_from_tags $INSTANCE_ID)

if [[ $INSTANCE_NAME =~ 'delivery' ]]; then
    msg "NO ELBs for delivery"
    exit 0
fi

get_elb_name_for_instance_name $INSTANCE_NAME
get_elb_list $INSTANCE_ID $ELB_NAME

msg "Checking that user set at least one load balancer"
if test -z "$ELB_LIST"; then
    error_exit "Must have at least one load balancer to deregister from"
fi

# Loop through all LBs the user set, and attempt to deregister this instance from them.
for elb in $ELB_LIST; do
    msg "Checking validity of load balancer named '$elb'"
    validate_elb $INSTANCE_ID $elb
    if [ $? != 0 ]; then
        msg "Error validating $elb; cannot continue with this LB"
        continue
    fi

    msg "Deregistering $INSTANCE_ID from $elb"
    deregister_instance $INSTANCE_ID $elb

    if [ $? != 0 ]; then
        error_exit "Failed to deregister instance $INSTANCE_ID from ELB $elb"
    fi
done

# Wait for all Deregistrations to finish
msg "Waiting for instance to de-register from its load balancers"
for elb in $ELB_LIST; do
    wait_for_state "elb" $INSTANCE_ID "OutOfService" $elb
    if [ $? != 0 ]; then
        error_exit "Failed waiting for $INSTANCE_ID to leave $elb"
    fi
done

msg "Finished $(basename $0) at $(/bin/date "+%F %T")"

end_sec=$(/bin/date +%s.%N)
elapsed_seconds=$(echo "$end_sec - $start_sec" | /usr/bin/bc)

msg "Elapsed time: $elapsed_seconds"
