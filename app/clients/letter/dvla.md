# DVLA API spike/prototyping

# Questions, thoughts, comments, concerns

- Can a malicious third-party try to authenticate (for a JWT token) with our username and cause DVLA to lock us out?
  How long for? What's the recovery process?
- When we lock ourselves out of changing our password automatically, and then do a manual reset (via email code),
  are we able to immediately change our password again programmatically?
  - No. How long are we blocked out from changing? Will it recover automatically or do we need to get in touch?
    - The following morning (12-24 hours later) we were able to rotate the password again, so it appears to be a
      temporary lockout. However, it remains trivially-simple for a random third-party to stop us from "ever"
      rotating our password automatically with only thge knowledge of the API endpoint and our username.
- Rotated API keys don't seem to be immediately valid - or JWT keys generated from fresh API keys don't seem to work
  immediately? Is there a few seconds delay or some synchronisation issue across authentication API and print
  letters API?
  - There's a few seconds synchronisation delay. We can continue using the old API key until we start getting auth
    errors, and then we can pull the new token from the cred store and use that.
