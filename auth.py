"""
Google OAuth Authentication Module for Vision Stack 2026
Handles user authentication and session management using Google OAuth.
"""
import streamlit as st
import os
import requests
import json
import base64

# Google OAuth Configuration
GOOGLE_CLIENT_ID = None
GOOGLE_CLIENT_SECRET = None
# Get redirect URI from environment (production) or default to localhost (development)
REDIRECT_URI = os.getenv("STREAMLIT_SERVER_URL", os.getenv("REDIRECT_URI", "http://localhost:8501"))

def init_oauth_config():
    """
    Initialize OAuth configuration from st.secrets (production) or environment variables (development).
    """
    global GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    
    try:
        # Try st.secrets first (production)
        GOOGLE_CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID", None)
        GOOGLE_CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET", None)
    except Exception:
        # Fallback to environment variables (development)
        GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", None)
        GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", None)
    
    # Use provided credentials if not in secrets/env
    if not GOOGLE_CLIENT_ID:
        GOOGLE_CLIENT_ID = "88626840204-b6r14t805ieraj95ucrn0s8lmsphlrsl.apps.googleusercontent.com"
    if not GOOGLE_CLIENT_SECRET:
        GOOGLE_CLIENT_SECRET = "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"
    
    return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

def get_google_oauth_url(state=None):
    """
    Generate Google OAuth authorization URL.
    
    Args:
        state: Optional state parameter for OAuth flow
    
    Returns:
        str: Google OAuth authorization URL
    """
    client_id, _ = init_oauth_config()
    redirect_uri = REDIRECT_URI
    
    # Google OAuth 2.0 authorization endpoint
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        "scope=openid email profile&"
        f"state={state or 'default'}&"
        "access_type=offline&"
        "prompt=consent"
    )
    return auth_url

def exchange_code_for_token(code):
    """
    Exchange OAuth authorization code for access token.
    
    Args:
        code: Authorization code from OAuth callback
    
    Returns:
        dict: Token response with access_token, id_token, etc.
    """
    client_id, client_secret = init_oauth_config()
    redirect_uri = REDIRECT_URI
    
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error exchanging code for token: {e}")
        return None

def get_user_info_from_token(access_token):
    """
    Get user information from Google using access token.
    
    Args:
        access_token: Google OAuth access token
    
    Returns:
        dict: User information (email, name, etc.)
    """
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(userinfo_url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching user info: {e}")
        return None

def get_id_token_email(id_token):
    """
    Decode JWT ID token to extract user email (simplified version).
    For production, use a proper JWT library like PyJWT.
    
    Args:
        id_token: Google OAuth ID token (JWT)
    
    Returns:
        str: User email or None
    """
    try:
        # Simple base64 decode of JWT payload (not production-grade, but works for email extraction)
        parts = id_token.split('.')
        if len(parts) >= 2:
            # Decode payload (second part)
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            user_data = json.loads(decoded)
            return user_data.get('email', None)
    except Exception:
        # Fallback: use access token to get user info
        return None

def authenticate_user():
    """
    Main authentication function. Checks if user is authenticated and handles OAuth flow.
    
    Returns:
        str: User email (user_id) if authenticated, None otherwise
    """
    # Initialize OAuth config
    init_oauth_config()
    
    # Check if user is already authenticated in session state
    if 'authenticated' in st.session_state and st.session_state.authenticated:
        if 'user_email' in st.session_state:
            return st.session_state.user_email
    
    # Check URL parameters for OAuth callback
    query_params = st.query_params
    
    # Check if we have an authorization code from OAuth callback
    if 'code' in query_params:
        code = query_params['code']
        
        # Exchange code for token
        token_response = exchange_code_for_token(code)
        
        if token_response and 'access_token' in token_response:
            access_token = token_response['access_token']
            id_token = token_response.get('id_token', None)
            
            # Get user email
            user_email = None
            
            # Try to get email from ID token first
            if id_token:
                user_email = get_id_token_email(id_token)
            
            # Fallback to userinfo API
            if not user_email:
                user_info = get_user_info_from_token(access_token)
                if user_info:
                    user_email = user_info.get('email', None)
                    # Store additional user info
                    st.session_state.user_name = user_info.get('name', '')
                    st.session_state.user_picture = user_info.get('picture', '')
            
            if user_email:
                # User is authenticated - set session state
                st.session_state.authenticated = True
                st.session_state.user_email = user_email
                st.session_state.user_id = user_email  # Use email as user_id for sandbox
                st.session_state.access_token = access_token
                
                # Clear query params to avoid re-authentication on refresh
                st.query_params.clear()
                
                # Trigger rerun to show authenticated UI
                st.rerun()
                
                return user_email
    
    # User is not authenticated
    st.session_state.authenticated = False
    return None

def render_login_page():
    """
    Render the login page UI with 'Sign in with Google' button.
    """
    st.set_page_config(page_title="Login - Vision Stack 2026", layout="centered", initial_sidebar_state="collapsed")
    
    # Hide default Streamlit menu and footer
    hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)
    
    # Centered login container
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        
        # Logo/Title
        st.markdown("""
        <div style="text-align: center;">
            <h1>👤 Vision Stack 2026</h1>
            <h3 style="color: #666;">Your Autonomous Digital Recruitment Agent</h3>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # Google Sign-In Button
        auth_url = get_google_oauth_url(state="login")
        
        st.markdown("""
        <div style="text-align: center;">
            <a href="{}" style="
                display: inline-block;
                padding: 12px 24px;
                background-color: #4285F4;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                font-weight: 500;
                font-size: 16px;
                transition: background-color 0.3s;
            ">
                🔐 Sign in with Google
            </a>
        </div>
        """.format(auth_url), unsafe_allow_html=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # Info text
        st.markdown("""
        <div style="text-align: center; color: #666; font-size: 14px;">
            Secure authentication with Google OAuth 2.0<br>
            Your data is protected and sandboxed per user
        </div>
        """, unsafe_allow_html=True)

def check_user_onboarding():
    """
    Check if user's directory exists. If not, they need to upload a CV.
    
    Returns:
        bool: True if user is onboarded (has profile_data.json), False otherwise
    """
    from utils import get_user_file_path
    
    if 'user_id' not in st.session_state:
        return False
    
    user_id = st.session_state.user_id
    profile_path = get_user_file_path('profile_data.json', user_id)
    
    return os.path.exists(profile_path) and os.path.getsize(profile_path) > 0

def require_auth(func):
    """
    Decorator to require authentication before running a function.
    
    Usage:
        @require_auth
        def my_protected_function():
            # This function only runs if user is authenticated
            pass
    """
    def wrapper(*args, **kwargs):
        user_email = authenticate_user()
        
        if not user_email:
            render_login_page()
            st.stop()
            return None
        
        # Check user onboarding
        if not check_user_onboarding():
            # Redirect to CV upload tab
            if 'active_tab' not in st.session_state:
                st.session_state.active_tab = 'upload_cv'
            st.info("👋 Welcome! Please upload your CV to get started.")
        
        return func(*args, **kwargs)
    
    return wrapper
