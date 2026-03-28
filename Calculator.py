import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

PROFILE_FILE = Path("profiles.json")
MAX_FDS = 3
MAX_EXPENSES = 5
CRORE = 1e7


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


def _is_defined_number(value):
    return not (isinstance(value, float) and math.isnan(value))


def load_profiles() -> dict:
    if PROFILE_FILE.exists():
        try:
            return json.loads(PROFILE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_profiles(profiles: dict):
    PROFILE_FILE.write_text(json.dumps(profiles, indent=2))


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
    for key, default in DEFAULT_STATE.items():
        if key not in st.session_state or st.session_state[key] is None:
            st.session_state[key] = default


def apply_pending_profile_reset():
    if st.session_state.pop("pending_profile_reset", False):
        st.session_state["profile_selection"] = "New profile"
        st.session_state["profile_save_name"] = ""


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


def load_profile_to_state(profile_name: str, profiles: dict):
    profile = profiles.get(profile_name)
    if not profile:
        return
    st.session_state["pending_profile"] = profile
    st.session_state["profile_loaded_from"] = profile_name
    st.session_state["profile_save_name"] = profile_name
    st.rerun()


def save_current_profile():
    name = (st.session_state.get("profile_save_name") or selected_profile).strip()
    if not name:
        st.error("Provide a name to save the profile.")
        return
    snapshots = load_profiles()
    snapshots[name] = assemble_payload()
    save_profiles(snapshots)
    st.success(f"Profile '{name}' saved.")


def delete_profile(profile_name: str):
    snapshots = load_profiles()
    if profile_name not in snapshots:
        st.warning(f"Profile '{profile_name}' was not found.")
        return
    del snapshots[profile_name]
    save_profiles(snapshots)
    st.session_state["pending_profile_reset"] = True
    st.success(f"Profile '{profile_name}' deleted.")
    st.rerun()


@st.dialog("Delete profile?")
def confirm_delete_profile_dialog(profile_name: str):
    st.write(f"Delete profile '{profile_name}'? This action cannot be undone.")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("Delete", type="primary", key="confirm_delete_profile_button"):
            delete_profile(profile_name)
    with cancel_col:
        if st.button("Cancel", key="cancel_delete_profile_button"):
            st.rerun()


st.set_page_config(layout="wide")
st.title("📊 Personal Wealth Dashboard")

initialize_session_state()
apply_pending_profile_reset()
apply_pending_profile()
profiles = load_profiles()

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

profile_names = ["New profile"] + sorted(profiles.keys())
if st.session_state.get("profile_selection") not in profile_names:
    st.session_state["profile_selection"] = "New profile"
profile_col1, profile_col2, profile_col3 = st.columns([2, 1, 1])
with profile_col1:
    selected_profile = st.selectbox(
        "Load saved profile",
        profile_names,
        key="profile_selection",
    )
    if st.button("Load profile", key="load_profile_button"):
        if selected_profile != "New profile":
            load_profile_to_state(selected_profile, profiles)
        else:
            st.warning("Pick a stored profile to load.")
with profile_col2:
    st.text_input(
        "Profile name to save",
        key="profile_save_name",
    )
    st.button(
        "Save profile",
        on_click=save_current_profile,
        key="save_profile_button",
    )
with profile_col3:
    st.write("")
    st.write("")
    if st.button(
        "Delete profile",
        key="delete_profile_button",
        disabled=selected_profile == "New profile",
    ):
        confirm_delete_profile_dialog(selected_profile)

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
                _is_defined_number(value)
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
