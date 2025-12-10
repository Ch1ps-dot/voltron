You are a developer of a protocol fuzzer. Now, please use Python to write a function based on the function prototype. This function is used to generate $msg_type messages in the $pro_name protocol. The following are the specific requirements and function prototype:

```python
def generate_$pending():
    """Complete this function with following requirements:
    1. Technology stack: Python, using only built-in libraries and no third-party packages
    2. Input: no input
    3. Output: required protocol message in bytes format.
    """
    
    messgae = ''
    
    # writing python code to complete the function
    
    return message
```

This is an one shot example of a Python function for generating FTP CWD command messages:

```python
import random
import string

def generate_ftp_cwd():
    # generating a random fields in limited scope
    path_length = random.randint(1, 255)  # the max length of FTP will not exceed 255
    path = ''.join(random.choices(string.ascii_letters + string.digits + "/._-", k=path_length))
    # construct CWD command message
    ftp_packet = f"CWD {path}\r\n"
    return ftp_packet
```

Only return the completed python function code.
