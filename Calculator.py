import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except ImportError:
    psycopg = None
    dict_row = None
    Json = None

PROFILE_FILE = Path("profiles.json")
SCHEMA_SQL_FILE = Path("sql/user_profiles.sql")
MAX_FDS = 3
MAX_EXPENSES = 5
CRORE = 1e7

LOCAL_MODE = "local"
CLOUD_MODE = "cloud"
MISCONFIGURED_MODE = "misconfigured"


@dataclass(frozen=True)
class UserIdentity:
    issuer: str
    subject: str
    email: str
    display_name: str

    @property
    def key(self) -> str:
        return f"{self.issuer}|{self.subject}"


def future_value(p: float, r: float, t: float) -> float:
    return p * (1 + r / 100) ** t


def stepup_sip(monthly: float, rate: float, years: int, stepup: float):
    value = 0.0
    values = []
    r = rate / 100 / 12

    for y in range(years):
        monthly = monthly * (1 + stepup / 100) if y > 0 else monthly
        for _ in range(12):
            value = (value + monthly) * (1 + r)
            values.append(value)

    return value, values


def is_defined_number(value: Any):
    return not (isinstance(value, float) and math.isnan(value))


def load_local_profiles() -> dict:
    if PROFILE_FILE.exists():
        try:
            return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_local_profiles(profiles: dict):
    PROFILE_FILE.write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def get_secret(name: str, default: str | None = None) -> str | None:
    try:
        return st.secrets[name]
    except Exception:
        return os.environ.get(name, default)


def to_crores(value: float) -> float:
    return value / CRORE if value else 0.0


def gather_profile_keys() -> list:
    keys = [
        "start_year",
        "projection_years",
        "use_fd",
        "use_stock",
        "use_mf",
        "use_sip",
        "stock_value",
        "stock_rate",
        "mf_value",
        "mf_rate",
        "sip_monthly",
        "sip_rate",
        "sip_step",
        "emergency",
        "insurance",
        "exp_count",
    ]
    for i in range(MAX_FDS):
        keys.extend([f"fd_amount{i}", f"fd_rate{i}"])
    for i in range(MAX_EXPENSES):
        keys.extend([f"exp_name{i}", f"exp_year{i}", f"exp_amount{i}"])
    return keys


PROFILE_KEYS = gather_profile_keys()


def build_default_state() -> dict:
    current_year = datetime.now().year
    defaults = {
        "start_year": current_year,
        "projection_years": 10,
        "use_fd": False,
        "use_stock": False,
        "use_mf": False,
        "use_sip": False,
        "stock_value": 0.0,
        "stock_rate": 0.0,
        "mf_value": 0.0,
        "mf_rate": 0.0,
        "sip_monthly": 0.0,
        "sip_rate": 0.0,
        "sip_step": 0.0,
        "emergency": 0.0,
        "insurance": 0.0,
        "exp_count": 0,
    }
    for i in range(MAX_FDS):
        defaults[f"fd_amount{i}"] = 0.0
        defaults[f"fd_rate{i}"] = 0.0
    for i in range(MAX_EXPENSES):
        defaults[f"exp_name{i}"] = ""
        defaults[f"exp_year{i}"] = current_year
        defaults[f"exp_amount{i}"] = 0.0
    return defaults


DEFAULT_STATE = build_default_state()


def normalize_profile(profile: dict | None) -> dict:
    normalized = DEFAULT_STATE.copy()
    if isinstance(profile, dict):
        for key in PROFILE_KEYS:
            value = profile.get(key)
            normalized[key] = DEFAULT_STATE[key] if value is None else value
    return normalized


def initialize_session_state():
    state_defaults = {
        "profile_selection": "New profile",
        "profile_save_name": "",
        "profile_loaded_from": "",
        "pending_profile": None,
        "pending_profile_reset": False,
        "pending_full_reset": False,
        "flash_message": None,
        "active_principal": None,
        "guest_mode_selected": False,
    }
    for key, default in DEFAULT_STATE.items():
        if key not in st.session_state or st.session_state[key] is None:
            st.session_state[key] = default
    for key, default in state_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def reset_form_state():
    for key, default in DEFAULT_STATE.items():
        st.session_state[key] = default
    st.session_state["profile_selection"] = "New profile"
    st.session_state["profile_save_name"] = ""
    st.session_state["profile_loaded_from"] = ""
    st.session_state["pending_profile"] = None


def apply_pending_full_reset():
    if st.session_state.pop("pending_full_reset", False):
        reset_form_state()


def apply_pending_profile_reset():
    if st.session_state.pop("pending_profile_reset", False):
        st.session_state["profile_selection"] = "New profile"
        st.session_state["profile_save_name"] = ""
        st.session_state["profile_loaded_from"] = ""


def apply_pending_profile():
    pending = st.session_state.pop("pending_profile", None)
    if isinstance(pending, dict):
        for key, value in normalize_profile(pending).items():
            st.session_state[key] = value


def assemble_payload() -> dict:
    return {
        key: DEFAULT_STATE[key]
        if st.session_state.get(key) is None
        else st.session_state.get(key)
        for key in PROFILE_KEYS
    }


def auth_is_available() -> bool:
    return hasattr(st.user, "is_logged_in")


def is_logged_in() -> bool:
    return auth_is_available() and bool(getattr(st.user, "is_logged_in", False))


def get_current_user() -> UserIdentity | None:
    if not is_logged_in():
        return None

    user_data = st.user.to_dict() if hasattr(st.user, "to_dict") else dict(st.user)
    issuer = str(user_data.get("iss") or "")
    subject = str(user_data.get("sub") or user_data.get("email") or "")
    email = str(
        user_data.get("email")
        or user_data.get("preferred_username")
        or user_data.get("upn")
        or ""
    )
    display_name = str(
        user_data.get("name")
        or user_data.get("given_name")
        or email
        or "Signed-in user"
    )
    if not issuer or not subject:
        return None
    return UserIdentity(
        issuer=issuer,
        subject=subject,
        email=email,
        display_name=display_name,
    )


def get_app_mode() -> str:
    db_configured = bool(get_secret("SUPABASE_DB_URL"))
    auth_configured = auth_is_available()
    if db_configured and auth_configured:
        return CLOUD_MODE
    if not db_configured and not auth_configured:
        return LOCAL_MODE
    return MISCONFIGURED_MODE


def get_active_principal(mode: str, user_identity: UserIdentity | None) -> str:
    if mode == LOCAL_MODE:
        return LOCAL_MODE
    if user_identity:
        return user_identity.key
    return "guest"


def sync_principal_state(mode: str, user_identity: UserIdentity | None):
    principal = get_active_principal(mode, user_identity)
    previous_principal = st.session_state.get("active_principal")
    if previous_principal is None:
        st.session_state["active_principal"] = principal
        return
    if previous_principal != principal:
        st.session_state["active_principal"] = principal
        st.session_state["pending_full_reset"] = True
        if principal != LOCAL_MODE:
            st.session_state["guest_mode_selected"] = principal == "guest"


def flash(level: str, message: str):
    st.session_state["flash_message"] = {"level": level, "message": message}


def render_flash_message():
    payload = st.session_state.pop("flash_message", None)
    if not payload:
        return
    level = payload["level"]
    message = payload["message"]
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)


def get_auth_provider_name() -> str | None:
    try:
        auth_config = st.secrets["auth"]
    except Exception:
        return None
    try:
        if "google" in auth_config:
            return "google"
    except Exception:
        return None
    return None


def login_with_google():
    provider_name = get_auth_provider_name()
    if provider_name:
        st.login(provider_name)
    else:
        st.login()


def continue_as_guest():
    st.session_state["guest_mode_selected"] = True
    flash("info", "Guest mode active. Sign in to save and manage cloud profiles.")
    st.rerun()


def logout_current_user():
    st.session_state["pending_full_reset"] = True
    st.session_state["guest_mode_selected"] = True
    st.logout()


def load_schema_sql() -> str:
    if SCHEMA_SQL_FILE.exists():
        return SCHEMA_SQL_FILE.read_text(encoding="utf-8")
    return """
    create schema if not exists private;

    create table if not exists private.user_profiles (
        id bigint generated by default as identity primary key,
        issuer text not null,
        subject text not null,
        email text,
        profile_name text not null,
        payload jsonb not null,
        created_at timestamptz not null default timezone('utc', now()),
        updated_at timestamptz not null default timezone('utc', now()),
        unique (issuer, subject, profile_name)
    );

    create index if not exists idx_user_profiles_user
        on private.user_profiles (issuer, subject);
    """


@st.cache_resource(show_spinner=False)
def ensure_database_schema(db_url: str):
    if psycopg is None or Json is None or dict_row is None:
        raise RuntimeError(
            "Database support requires psycopg. Install requirements.txt before using cloud profiles."
        )

    try:
        with psycopg.connect(db_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(load_schema_sql())
    except Exception as exc:
        raise RuntimeError(
            "Could not initialize the Supabase profile table. "
            "Check SUPABASE_DB_URL and run the setup SQL if your DB user cannot create schemas."
        ) from exc


def run_db_query(query: str, params: tuple = (), fetch: str | None = None):
    db_url = get_secret("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is missing.")

    ensure_database_schema(db_url)

    try:
        with psycopg.connect(db_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                if fetch == "one":
                    result = cursor.fetchone()
                elif fetch == "all":
                    result = cursor.fetchall()
                else:
                    result = None
            connection.commit()
        return result
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Supabase profile storage is unavailable right now. Verify your database URL and permissions."
        ) from exc


def list_profiles(user_identity: UserIdentity | None) -> list[str]:
    mode = get_app_mode()
    if mode == LOCAL_MODE:
        return sorted(load_local_profiles().keys())
    if mode == CLOUD_MODE and user_identity:
        rows = run_db_query(
            """
            select profile_name
            from private.user_profiles
            where issuer = %s and subject = %s
            order by profile_name
            """,
            (user_identity.issuer, user_identity.subject),
            fetch="all",
        )
        return [row["profile_name"] for row in rows or []]
    return []


def load_profile(user_identity: UserIdentity | None, profile_name: str) -> dict | None:
    mode = get_app_mode()
    if mode == LOCAL_MODE:
        return normalize_profile(load_local_profiles().get(profile_name))
    if mode == CLOUD_MODE and user_identity:
        row = run_db_query(
            """
            select payload
            from private.user_profiles
            where issuer = %s and subject = %s and profile_name = %s
            """,
            (user_identity.issuer, user_identity.subject, profile_name),
            fetch="one",
        )
        if not row:
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return normalize_profile(payload)
    return None


def save_profile(user_identity: UserIdentity | None, profile_name: str, payload: dict):
    normalized_payload = normalize_profile(payload)
    mode = get_app_mode()
    if mode == LOCAL_MODE:
        profiles = load_local_profiles()
        profiles[profile_name] = normalized_payload
        save_local_profiles(profiles)
        return
    if mode == CLOUD_MODE:
        if user_identity is None:
            raise PermissionError("Sign in with Google to save profiles online.")
        run_db_query(
            """
            insert into private.user_profiles (
                issuer, subject, email, profile_name, payload, created_at, updated_at
            )
            values (
                %s, %s, %s, %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            on conflict (issuer, subject, profile_name)
            do update set
                email = excluded.email,
                payload = excluded.payload,
                updated_at = timezone('utc', now())
            """,
            (
                user_identity.issuer,
                user_identity.subject,
                user_identity.email,
                profile_name,
                Json(normalized_payload),
            ),
        )
        return
    raise RuntimeError(
        "Cloud profile storage is not fully configured. Add both authentication secrets and SUPABASE_DB_URL."
    )


def delete_profile(user_identity: UserIdentity | None, profile_name: str):
    mode = get_app_mode()
    if mode == LOCAL_MODE:
        profiles = load_local_profiles()
        if profile_name not in profiles:
            raise KeyError(profile_name)
        del profiles[profile_name]
        save_local_profiles(profiles)
        return
    if mode == CLOUD_MODE:
        if user_identity is None:
            raise PermissionError("Sign in with Google to delete profiles.")
        deleted = run_db_query(
            """
            delete from private.user_profiles
            where issuer = %s and subject = %s and profile_name = %s
            returning id
            """,
            (user_identity.issuer, user_identity.subject, profile_name),
            fetch="one",
        )
        if not deleted:
            raise KeyError(profile_name)
        return
    raise RuntimeError(
        "Cloud profile storage is not fully configured. Add both authentication secrets and SUPABASE_DB_URL."
    )


def import_seed_profiles(user_identity: UserIdentity | None) -> int:
    if user_identity is None:
        raise PermissionError("Sign in with Google to import profiles.")

    seed_profiles = load_local_profiles()
    if not seed_profiles:
        return 0

    count = 0
    for name, profile in seed_profiles.items():
        save_profile(user_identity, name, profile)
        count += 1
    return count


def load_profile_to_state(profile_name: str, user_identity: UserIdentity | None):
    profile = load_profile(user_identity, profile_name)
    if not profile:
        st.warning(f"Profile '{profile_name}' was not found.")
        return
    st.session_state["pending_profile"] = profile
    st.session_state["profile_loaded_from"] = profile_name
    st.session_state["profile_save_name"] = profile_name
    flash("success", f"Profile '{profile_name}' loaded.")
    st.rerun()


def save_current_profile(user_identity: UserIdentity | None):
    name = (
        st.session_state.get("profile_save_name")
        or st.session_state.get("profile_loaded_from")
        or ""
    ).strip()
    if not name:
        st.error("Provide a profile name before saving.")
        return
    try:
        save_profile(user_identity, name, assemble_payload())
    except PermissionError as exc:
        st.error(str(exc))
        return
    except RuntimeError as exc:
        st.error(str(exc))
        return
    st.session_state["profile_loaded_from"] = name
    st.success(f"Profile '{name}' saved.")


def delete_selected_profile(profile_name: str, user_identity: UserIdentity | None):
    try:
        delete_profile(user_identity, profile_name)
    except KeyError:
        flash("warning", f"Profile '{profile_name}' was not found.")
    except PermissionError as exc:
        flash("error", str(exc))
    except RuntimeError as exc:
        flash("error", str(exc))
    else:
        st.session_state["pending_profile_reset"] = True
        flash("success", f"Profile '{profile_name}' deleted.")
    st.rerun()


@st.dialog("Delete profile?")
def confirm_delete_profile_dialog(profile_name: str, user_identity: UserIdentity | None):
    st.write(f"Delete profile '{profile_name}'? This action cannot be undone.")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("Delete", type="primary", key="confirm_delete_profile_button"):
            delete_selected_profile(profile_name, user_identity)
    with cancel_col:
        if st.button("Cancel", key="cancel_delete_profile_button"):
            st.rerun()


def render_auth_section(mode: str, user_identity: UserIdentity | None):
    with st.container(border=True):
        st.subheader("Access")

        if mode == LOCAL_MODE:
            st.info(
                "Local single-user mode is active. Profiles save to profiles.json on this machine."
            )
            return

        if mode == MISCONFIGURED_MODE:
            st.error(
                "Cloud mode is partially configured. Add both Streamlit OIDC auth secrets and "
                "SUPABASE_DB_URL to enable per-user profile storage."
            )
            if auth_is_available() and not user_identity:
                action_col1, action_col2 = st.columns([1, 1])
                with action_col1:
                    if st.button("Continue as guest", key="continue_as_guest_button"):
                        continue_as_guest()
                with action_col2:
                    if st.button("Log in with Google", key="login_google_button"):
                        login_with_google()
            elif user_identity:
                info_col1, info_col2 = st.columns([4, 1])
                with info_col1:
                    st.write(
                        f"Signed in as **{user_identity.display_name}** "
                        f"({user_identity.email or 'email unavailable'})"
                    )
                with info_col2:
                    if st.button("Log out", key="logout_button"):
                        logout_current_user()
            return

        if user_identity:
            action_cols = st.columns([4, 1, 1])
            with action_cols[0]:
                st.success(
                    f"Signed in as {user_identity.display_name} "
                    f"({user_identity.email or 'email unavailable'})"
                )
            with action_cols[1]:
                import_disabled = len(load_local_profiles()) == 0
                if st.button(
                    "Import local profiles",
                    key="import_local_profiles_button",
                    disabled=import_disabled,
                ):
                    try:
                        imported_count = import_seed_profiles(user_identity)
                    except (PermissionError, RuntimeError) as exc:
                        flash("error", str(exc))
                    else:
                        flash(
                            "success",
                            f"Imported or updated {imported_count} profile(s) from profiles.json.",
                        )
                    st.rerun()
            with action_cols[2]:
                if st.button("Log out", key="logout_button"):
                    logout_current_user()
            return

        info_text = (
            "Guest mode is active. You can use the calculator, but saving, loading, and deleting "
            "profiles requires sign-in."
            if st.session_state.get("guest_mode_selected")
            else "Choose how to continue. Guest mode works immediately, and Google sign-in "
            "unlocks your private cloud profiles."
        )
        action_cols = st.columns([4, 1, 1])
        with action_cols[0]:
            st.info(info_text)
        with action_cols[1]:
            if st.button("Continue as guest", key="continue_as_guest_button"):
                continue_as_guest()
        with action_cols[2]:
            if st.button("Log in with Google", key="login_google_button"):
                login_with_google()


def get_profile_section_state(mode: str, user_identity: UserIdentity | None):
    if mode == LOCAL_MODE:
        return {"names": list_profiles(user_identity), "disabled": False, "error": None}
    if mode == CLOUD_MODE and user_identity:
        try:
            return {"names": list_profiles(user_identity), "disabled": False, "error": None}
        except RuntimeError as exc:
            return {"names": [], "disabled": True, "error": str(exc)}
    if mode == CLOUD_MODE:
        return {"names": [], "disabled": True, "error": None}
    return {"names": [], "disabled": True, "error": None}


st.set_page_config(layout="wide")
st.title("Personal Wealth Dashboard")

initialize_session_state()
current_user = get_current_user()
app_mode = get_app_mode()
sync_principal_state(app_mode, current_user)
apply_pending_full_reset()
apply_pending_profile_reset()
apply_pending_profile()

render_flash_message()
render_auth_section(app_mode, current_user)

profile_state = get_profile_section_state(app_mode, current_user)
profile_names = ["New profile"] + profile_state["names"]
if st.session_state.get("profile_selection") not in profile_names:
    st.session_state["profile_selection"] = "New profile"

if app_mode == LOCAL_MODE:
    st.caption("Profiles are stored locally in profiles.json.")
elif app_mode == CLOUD_MODE and current_user:
    st.caption("Your saved profiles are stored in Supabase and scoped to your account.")
elif app_mode == CLOUD_MODE:
    st.caption("Guest mode does not persist profiles. Sign in to access cloud storage.")
else:
    st.caption(
        "Profile storage is unavailable until authentication and database secrets are configured."
    )

if profile_state["error"]:
    st.error(profile_state["error"])

summary_col1, summary_col2, summary_col3 = st.columns(3)
with summary_col1:
    start_year = st.number_input(
        "Projection start year",
        min_value=2000,
        max_value=2100,
        key="start_year",
    )
with summary_col2:
    projection_years = st.slider(
        "Projection horizon (years)",
        min_value=1,
        max_value=30,
        key="projection_years",
    )
with summary_col3:
    st.markdown(
        f"**Ends in:** {int(start_year) + int(projection_years) - 1}"
    )

profile_controls_disabled = profile_state["disabled"]
profile_col1, profile_col2, profile_col3 = st.columns([2, 1, 1])
with profile_col1:
    selected_profile = st.selectbox(
        "Load saved profile",
        profile_names,
        key="profile_selection",
        disabled=profile_controls_disabled,
    )
    if st.button(
        "Load profile",
        key="load_profile_button",
        disabled=profile_controls_disabled,
    ):
        if selected_profile != "New profile":
            load_profile_to_state(selected_profile, current_user)
        else:
            st.warning("Pick a stored profile to load.")
with profile_col2:
    st.text_input(
        "Profile name to save",
        key="profile_save_name",
        disabled=profile_controls_disabled,
    )
    if st.button(
        "Save profile",
        key="save_profile_button",
        disabled=profile_controls_disabled,
    ):
        save_current_profile(current_user)
with profile_col3:
    st.write("")
    st.write("")
    if st.button(
        "Delete profile",
        key="delete_profile_button",
        disabled=profile_controls_disabled or selected_profile == "New profile",
    ):
        confirm_delete_profile_dialog(selected_profile, current_user)

# ---------- TABS ----------
tab1, tab2, tab3, tab4 = st.tabs(
    ["🪙 Investments", "💸 Expenses", "🛡️ Safety", "📈 Summary"]
)

# ---------- TAB 1: INVESTMENTS ----------
fd_entries = []
stock_entry = None
mf_entry = None
sip_monthly_values = []
fd_total = 0.0
stock_total = 0.0
mf_total = 0.0
sip_total = 0.0

with tab1:
    st.header("Investments")

    use_fd = st.checkbox("Include FDs", key="use_fd")
    use_stock = st.checkbox("Include Stocks", key="use_stock")
    use_mf = st.checkbox("Include Mutual Funds", key="use_mf")
    use_sip = st.checkbox("Include SIP", key="use_sip")

    if use_fd:
        with st.expander("🏦 Fixed Deposits"):
            for i in range(MAX_FDS):
                amount = st.number_input(
                    f"FD #{i + 1} amount",
                    min_value=0.0,
                    step=1000.0,
                    key=f"fd_amount{i}",
                )
                rate = st.number_input(
                    f"FD #{i + 1} rate (%)",
                    min_value=0.0,
                    max_value=100.0,
                    key=f"fd_rate{i}",
                )
                if amount and rate:
                    fd_entries.append({"amount": float(amount), "rate": float(rate)})
                    fd_total += future_value(amount, rate, projection_years)
            st.caption(
                f"FD horizon total: ₹{fd_total:,.0f} ({to_crores(fd_total):,.2f} Cr)"
            )

    if use_stock:
        with st.expander("📈 Stocks"):
            stock_value = st.number_input(
                "Current value",
                min_value=0.0,
                step=1000.0,
                key="stock_value",
            )
            stock_rate = st.number_input(
                "CAGR (%)",
                min_value=0.0,
                max_value=100.0,
                key="stock_rate",
            )
            if stock_value and stock_rate:
                stock_entry = {"value": float(stock_value), "rate": float(stock_rate)}
                stock_total = future_value(stock_value, stock_rate, projection_years)
            st.caption(
                f"Stock future: ₹{stock_total:,.0f} ({to_crores(stock_total):,.2f} Cr)"
            )

    if use_mf:
        with st.expander("💼 Mutual Funds"):
            mf_value = st.number_input(
                "Current value",
                min_value=0.0,
                step=1000.0,
                key="mf_value",
            )
            mf_rate = st.number_input(
                "CAGR (%)",
                min_value=0.0,
                max_value=100.0,
                key="mf_rate",
            )
            if mf_value and mf_rate:
                mf_entry = {"value": float(mf_value), "rate": float(mf_rate)}
                mf_total = future_value(mf_value, mf_rate, projection_years)
            st.caption(
                f"MF future: ₹{mf_total:,.0f} ({to_crores(mf_total):,.2f} Cr)"
            )

    if use_sip:
        with st.expander("💹 Step-up SIP"):
            sip_monthly = st.number_input(
                "Monthly SIP",
                min_value=0.0,
                step=500.0,
                key="sip_monthly",
            )
            sip_rate = st.number_input(
                "Return (%)",
                min_value=0.0,
                max_value=100.0,
                key="sip_rate",
            )
            sip_step = st.number_input(
                "Step-up (%)",
                min_value=0.0,
                max_value=100.0,
                key="sip_step",
            )
            if not all(
                is_defined_number(value)
                for value in (sip_monthly, sip_rate, sip_step)
            ):
                st.warning("Complete all SIP inputs to compute future value.")
            else:
                sip_total, sip_monthly_values = stepup_sip(
                    float(sip_monthly), float(sip_rate), int(projection_years), float(sip_step)
                )
                st.caption(
                    f"SIP future: ₹{sip_total:,.0f} ({to_crores(sip_total):,.2f} Cr)"
                )

# ---------- TAB 2: EXPENSES ----------
expenses = []
total_expenses = 0.0
expense_schedule = defaultdict(float)
with tab2:
    st.header("Future Expenses")
    exp_count = st.number_input(
        "Number of expense entries",
        min_value=0,
        max_value=MAX_EXPENSES,
        key="exp_count",
    )

    for i in range(exp_count):
        if st.session_state.get(f"exp_year{i}") is None:
            st.session_state[f"exp_year{i}"] = int(start_year)
        name = st.text_input(
            f"Expense #{i + 1} name",
            key=f"exp_name{i}",
        )
        year = st.number_input(
            f"Expense #{i + 1} year",
            min_value=2000,
            max_value=2100,
            key=f"exp_year{i}",
        )
        amount = st.number_input(
            f"Expense #{i + 1} amount",
            min_value=0.0,
            step=1000.0,
            key=f"exp_amount{i}",
        )
        if amount:
            expenses.append({"name": name, "year": int(year), "amount": float(amount)})
            total_expenses += float(amount)
            expense_schedule[int(year)] += float(amount)
    st.caption(
        f"Total future expenses: ₹{total_expenses:,.0f} ({to_crores(total_expenses):,.2f} Cr)"
    )

# ---------- TAB 3: SAFETY ----------
with tab3:
    st.header("Safety Funds")
    emergency = st.number_input(
        "Emergency fund",
        min_value=0.0,
        step=1000.0,
        key="emergency",
    )
    insurance = st.number_input(
        "Insurance corpus",
        min_value=0.0,
        step=1000.0,
        key="insurance",
    )

total_safety = float(emergency) + float(insurance)

# ---------- CALCULATIONS ----------
asset_curve = [0.0] * int(projection_years)
for idx in range(int(projection_years)):
    step = idx + 1
    for fd in fd_entries:
        asset_curve[idx] += future_value(fd["amount"], fd["rate"], step)
    if stock_entry:
        asset_curve[idx] += future_value(
            stock_entry["value"], stock_entry["rate"], step
        )
    if mf_entry:
        asset_curve[idx] += future_value(
            mf_entry["value"], mf_entry["rate"], step
        )
    if sip_monthly_values:
        sip_idx = min(step * 12 - 1, len(sip_monthly_values) - 1)
        asset_curve[idx] += sip_monthly_values[sip_idx]

year_labels = [int(start_year) + i for i in range(int(projection_years))]
expense_yearly = [expense_schedule.get(year, 0.0) for year in year_labels]
cumulative_expenses = []
cum = 0.0
for value in expense_yearly:
    cum += value
    cumulative_expenses.append(cum)

net_curve = [
    asset_curve[i] - cumulative_expenses[i] - total_safety
    for i in range(len(asset_curve))
]

total_assets = fd_total + stock_total + mf_total + sip_total
net_total = total_assets - total_expenses - total_safety

asset_mix_values = [val for val in [fd_total, stock_total, mf_total, sip_total] if val > 0]
asset_mix_labels = [label for label, val in zip(
    ["FDs", "Stocks", "Mutual Funds", "SIP"],
    [fd_total, stock_total, mf_total, sip_total],
) if val > 0]

summary_df = pd.DataFrame(
    {
        "Year": year_labels,
        "Assets (Cr)": [to_crores(val) for val in asset_curve],
        "Expenses (Cr)": [to_crores(val) for val in cumulative_expenses],
        "Net (Cr)": [to_crores(val) for val in net_curve],
    }
)

with tab4:
    st.header("Wealth Summary")
    st.metric(
        "Total assets",
        f"₹{to_crores(total_assets):,.2f} Cr",
        f"SIP future value included: {to_crores(sip_total):,.2f} Cr",
    )
    st.metric(
        "Expenses (total)",
        f"₹{to_crores(total_expenses):,.2f} Cr",
    )
    st.metric(
        "Safety corpus",
        f"₹{to_crores(total_safety):,.2f} Cr",
    )
    st.metric(
        "Net future wealth",
        f"₹{to_crores(net_total):,.2f} Cr",
    )

    st.subheader("Yearly snapshot")
    st.dataframe(
        summary_df.style.format({"Assets (Cr)": "{:.2f}", "Expenses (Cr)": "{:.2f}", "Net (Cr)": "{:.2f}"})
    )

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].plot(year_labels, [to_crores(val) for val in asset_curve], marker="o")
    axes[0, 0].set_title("Assets (Cr)")
    axes[0, 0].set_ylabel("Crores")

    axes[0, 1].bar(year_labels, [to_crores(val) for val in expense_yearly], color="#d62728")
    axes[0, 1].set_title("Annual expenses (Cr)")

    axes[1, 0].plot(year_labels, [to_crores(val) for val in net_curve], marker="s", color="#2ca02c")
    axes[1, 0].set_title("Net wealth (Cr)")

    if asset_mix_values:
        axes[1, 1].pie(
            [to_crores(val) for val in asset_mix_values],
            labels=asset_mix_labels,
            autopct="%1.1f%%",
            startangle=90,
        )
        axes[1, 1].set_title("Asset mix (Cr)")
    else:
        axes[1, 1].text(0.5, 0.5, "Add investments to view mix", ha="center", va="center")
        axes[1, 1].axis("off")

    fig.tight_layout()
    st.pyplot(fig)
