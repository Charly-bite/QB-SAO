import os
from dotenv import dotenv_values

def test_sql_server_ip_is_correct():
    """
    Test to ensure that the SQL_SERVER environment variable 
    is set to the correct IP address (192.168.2.237) and has not 
    been accidentally changed to the local workstation's IP.
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    
    # Check if .env file exists
    assert os.path.exists(env_path), f".env file not found at {env_path}"
    
    # Load the values directly from the .env file
    config = dotenv_values(env_path)
    
    # Assert the IP is the correct database server IP
    assert 'SQL_SERVER' in config, "SQL_SERVER is missing from the .env file"
    assert config['SQL_SERVER'] == '192.168.2.237', (
        f"SQL_SERVER IP address changed! "
        f"Expected '192.168.2.237', but got '{config['SQL_SERVER']}'. "
        f"Make sure you don't confuse your local machine's IP with the Database Server IP."
    )
