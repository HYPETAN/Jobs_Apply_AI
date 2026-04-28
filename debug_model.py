from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# 🚨 PASTE THE SAME FOLDER ID YOU USE IN RESUME_FACTORY.PY 🚨
TARGET_FOLDER_ID = "1CdzlPliByhC4AsJ4hXbKQ23jeI1p_meR" 

SCOPES = ['https://www.googleapis.com/auth/drive']
print("--- 📂 DRIVE PERMISSIONS DEBUGGER ---")

try:
    # 1. Authenticate
    print("1. Authenticating...")
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)
    
    # 2. Check Folder Access
    print(f"2. Checking access to folder: {TARGET_FOLDER_ID}...")
    try:
        folder = service.files().get(fileId=TARGET_FOLDER_ID, fields="name, capabilities").execute()
        print(f"   ✅ FOUND FOLDER: '{folder.get('name')}'")
        
        can_edit = folder.get('capabilities', {}).get('canAddChildren', False)
        if can_edit:
            print("   ✅ PERMISSION CHECK: Robot has 'Editor' access.")
        else:
            print("   ❌ PERMISSION ERROR: Robot is a 'Viewer' only. Change to 'Editor'.")
            exit()
            
    except Exception as e:
        print(f"   ❌ FOLDER ERROR: Could not find folder. Check ID or Sharing.\n   {e}")
        exit()

    # 3. Test Upload
    print("3. Attempting test upload...")
    file_metadata = {
        'name': 'test_permissions.txt',
        'parents': [TARGET_FOLDER_ID]
    }
    media = MediaIoBaseUpload(io.BytesIO(b"Hello Google Drive"), mimetype='text/plain')
    
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"   🎉 SUCCESS! Created test file with ID: {file.get('id')}")
    
    # 4. Cleanup
    print("4. Deleting test file...")
    service.files().delete(fileId=file.get('id')).execute()
    print("   ✅ Cleanup complete.")
    
except Exception as e:
    print(f"\n❌ FATAL ERROR: {e}")