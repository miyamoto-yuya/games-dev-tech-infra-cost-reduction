#!/bin/bash
# Usage: source assume-role.sh <MFA_CODE>

if [ -z "$1" ]; then
    echo "Usage: source assume-role.sh <MFA_CODE>"
    return 1
fi

MFA_CODE=$1

CREDS=$(aws sts assume-role \
    --role-arn "arn:aws:iam::935762823806:role/techmng-administrator-role" \
    --role-session-name "terraform" \
    --serial-number "arn:aws:iam::225396806813:mfa/miyamotoy-pc" \
    --token-code "$MFA_CODE" \
    --profile infra-gw \
    --output json 2>&1)

if [ $? -ne 0 ]; then
    echo "Error: $CREDS"
    return 1
fi

export AWS_ACCESS_KEY_ID=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['AccessKeyId'])")
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['SecretAccessKey'])")
export AWS_SESSION_TOKEN=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['SessionToken'])")
unset AWS_PROFILE

echo "AWS credentials configured successfully!"
echo "Session expires at: $(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['Expiration'])")"

