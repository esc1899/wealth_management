"""
Einstellungen — Skills verwalten und mit KI generieren.
"""

import asyncio

import streamlit as st

from config import config
from core.llm.local import OllamaProvider
from core.llm.base import Message, Role
from core.storage.models import Skill
from state import get_skills_repo

st.set_page_config(page_title="Einstellungen", page_icon="⚙️", layout="wide")
st.title("Einstellungen")

skills_repo = get_skills_repo()

# ------------------------------------------------------------------
# Section: Skills list
# ------------------------------------------------------------------

st.subheader("Skills")

all_skills = skills_repo.get_all()

if not all_skills:
    st.info("Noch keine Skills vorhanden.")
else:
    # Group by area
    areas: dict[str, list] = {}
    for skill in all_skills:
        areas.setdefault(skill.area, []).append(skill)

    for area, area_skills in areas.items():
        st.markdown(f"**Bereich: {area}**")
        for skill in area_skills:
            with st.expander(f"{skill.name}" + (f" — {skill.description}" if skill.description else "")):
                st.markdown(f"**Beschreibung:** {skill.description or '–'}")
                st.markdown("**Prompt:**")
                st.code(skill.prompt, language=None)
                if st.button("Löschen", key=f"del_{skill.id}", type="secondary"):
                    skills_repo.delete(skill.id)
                    st.success(f"Skill '{skill.name}' gelöscht.")
                    st.rerun()

st.divider()

# ------------------------------------------------------------------
# Section: Add skill manually
# ------------------------------------------------------------------

st.subheader("Skill hinzufügen")

AREA_OPTIONS = ["research", "stock_search", "rebalancing", "portfolio_analysis", "Anderer…"]

with st.form("add_skill_form"):
    new_name = st.text_input("Name *", placeholder="z.B. Value Investing")
    area_choice = st.selectbox("Bereich *", AREA_OPTIONS)
    custom_area = ""
    if area_choice == "Anderer…":
        custom_area = st.text_input("Eigener Bereich *", placeholder="z.B. risk_analysis")
    new_description = st.text_input("Beschreibung (optional)", placeholder="Kurze Beschreibung des Skills")
    new_prompt = st.text_area("Prompt *", placeholder="Gib hier den Prompt-Text ein…", height=180)
    save_btn = st.form_submit_button("Skill speichern", use_container_width=True)

if save_btn:
    resolved_area = custom_area.strip() if area_choice == "Anderer…" else area_choice
    if not new_name.strip():
        st.error("Bitte einen Namen eingeben.")
    elif area_choice == "Anderer…" and not resolved_area:
        st.error("Bitte einen Bereich eingeben.")
    elif not new_prompt.strip():
        st.error("Bitte einen Prompt eingeben.")
    else:
        try:
            skill = Skill(
                name=new_name.strip(),
                area=resolved_area,
                description=new_description.strip() or None,
                prompt=new_prompt.strip(),
            )
            skills_repo.add(skill)
            st.success(f"Skill '{skill.name}' gespeichert.")
            st.rerun()
        except Exception as exc:
            st.error(f"Fehler beim Speichern: {exc}")

st.divider()

# ------------------------------------------------------------------
# Section: LLM-generated skill
# ------------------------------------------------------------------

st.subheader("Skill mit KI generieren")

gen_description = st.text_input(
    "Beschreibung des Anwendungsfalls",
    placeholder="z.B. Nachhaltigkeitsanalyse für ESG-Investitionen",
    key="gen_desc",
)
gen_area = st.selectbox("Bereich", AREA_OPTIONS[:-1], key="gen_area")

if st.button("Mit KI generieren", key="gen_btn"):
    if not gen_description.strip():
        st.error("Bitte eine Beschreibung eingeben.")
    else:
        with st.spinner("KI generiert Prompt…"):
            try:
                llm = OllamaProvider(host=config.OLLAMA_HOST, model=config.OLLAMA_MODEL)
                user_msg = (
                    f"Erstelle einen Investment-Analyse-Prompt für folgenden Anwendungsfall: "
                    f"{gen_description.strip()}. Bereich: {gen_area}. "
                    f"Antworte NUR mit dem Prompt-Text selbst, ohne Einleitung oder Erklärung."
                )
                generated = asyncio.run(llm.chat([Message(role=Role.USER, content=user_msg)]))
                st.session_state["gen_result"] = generated
            except Exception as exc:
                st.error(f"Fehler bei der KI-Generierung: {exc}")

if "gen_result" in st.session_state and st.session_state["gen_result"]:
    st.markdown("**Generierter Prompt** (bearbeitbar):")
    edited_prompt = st.text_area(
        "Prompt bearbeiten",
        value=st.session_state["gen_result"],
        height=200,
        key="gen_edit",
    )
    gen_save_name = st.text_input("Name für diesen Skill *", key="gen_save_name")
    gen_save_desc = st.text_input("Beschreibung (optional)", key="gen_save_desc")

    if st.button("Generierten Skill speichern", key="gen_save_btn"):
        if not gen_save_name.strip():
            st.error("Bitte einen Namen für den Skill eingeben.")
        elif not edited_prompt.strip():
            st.error("Prompt darf nicht leer sein.")
        else:
            try:
                skill = Skill(
                    name=gen_save_name.strip(),
                    area=gen_area,
                    description=gen_save_desc.strip() or None,
                    prompt=edited_prompt.strip(),
                )
                skills_repo.add(skill)
                st.success(f"Skill '{skill.name}' gespeichert.")
                del st.session_state["gen_result"]
                st.rerun()
            except Exception as exc:
                st.error(f"Fehler beim Speichern: {exc}")
