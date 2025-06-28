import os

def generate_env_script():
    """
    Reads the .env file and generates a Windows batch script 
    to set the environment variables.
    """
    try:
        with open('.env', 'r') as f_in:
            with open('set_env.bat', 'w') as f_out:
                f_out.write('@echo off\n')
                f_out.write('echo Setting environment variables...\n')
                for line in f_in:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        # Remove quotes from value if they exist
                        value = value.strip('"\'')
                        f_out.write(f'set "{key}={value}"\n')
                f_out.write('echo Environment variables set.\n')
                f_out.write('echo You can now run the main script.\n')
        print("Successfully created set_env.bat")
        print("Run 'set_env.bat' in your terminal before running the main application.")
    except FileNotFoundError:
        print("ERROR: .env file not found. Please create one with your credentials.")

if __name__ == "__main__":
    generate_env_script()