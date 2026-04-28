import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes = What permission we are asking for
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def login():
    print("--- 🔐 GOOGLE USER LOGIN ---")
    
    if not os.path.exists('client_secret.json'):
        print("❌ ERROR: 'client_secret.json' not found!")
        print("   -> Go to Google Cloud Console > Credentials > Create OAuth Client ID (Desktop).")
        print("   -> Download JSON, rename to 'client_secret.json', and place it here.")
        return

    try:
        # Launch browser to login
        flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Save the token for the main script to use
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
        print("\n✅ SUCCESS! Login complete.")
        print("   -> A file named 'token.json' has been created.")
        print("   -> Your Resume Factory can now upload files as YOU.")
        
    except Exception as e:
        print(f"\n❌ Login Failed: {e}")

if __name__ == '__main__':
    login()