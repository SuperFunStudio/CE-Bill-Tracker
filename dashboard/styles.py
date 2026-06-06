"""Shared CSS injected into every SignalScout dashboard page."""
import streamlit as st


def inject_shared_styles() -> None:
    st.markdown("""
<style>
    .block-container { padding-top: 2rem; }

    .section-header {
        color: #d1d5db;
        font-size: 1.1rem;
        font-weight: 600;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid #1f2937;
    }
</style>
""", unsafe_allow_html=True)
