# Lambda function

This code is used to setup a lambda function to call into our API to deliver messages.

Basic expected flow is that an request to GOV.UK Notify to send a text/email will persist in our DB then invoke an async lambda function. 

This function will call /deliver/notification/{id} which will make the API call to our delivery partners, updating the DB with the response.

## EXPERIMENTAL AT THIS STAGE
