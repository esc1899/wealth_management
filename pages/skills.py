"""
Skills Management — manage and AI-generate portfolio analysis skills/prompts.
"""

import asyncio
import logging
import streamlit as st

st.set_page_config(page_title="Skills", layout="wide")
st.title("🎯 Skills")

from core.i18n import t
from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.models import Skill
from config import config
from state import get_skills_repo

logger = logging.getLogger(__name__)

skills_repo = get_skills_repo()

# ------------------------------------------------------------------
# Section: Skills list
# ------------------------------------------------------------------

st.subheader(t("settings.skills_header"))

all_skills = skills_repo.get_all()

if not all_skills:
    st.info(t("settings.no_skills"))
else:
    # Group by area
    areas: dict[str, list] = {}
    for skill in all_skills:
        areas.setdefault(skill.area, []).append(skill)

    for area, area_skills in areas.items():
        st.markdown(f"**{t('settings.area_label')}: {area}**")
        for skill in area_skills:
            with st.expander(f"{skill.name}" + (f" — {skill.description}" if skill.description else "")):
                if st.session_state.get("editing_skill_id") == skill.id:
                    # --- Edit form ---
                    with st.form(key=f"edit_form_{skill.id}"):
                        edit_name = st.text_input(t("settings.name_label"), value=skill.name)
                        edit_area = st.text_input(t("settings.area_label_required"), value=skill.area)
                        edit_desc = st.text_input(t("settings.description_label"), value=skill.description or "")
                        edit_prompt = st.text_area(t("settings.prompt_label"), value=skill.prompt, height=180)
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            submitted = st.form_submit_button(t("settings.save_button"), use_container_width=True)
                        with col_cancel:
                            cancelled = st.form_submit_button(t("settings.cancel_button"), use_container_width=True)
                    if submitted:
                        if not edit_name.strip() or not edit_prompt.strip():
                            st.error(t("settings.name_required_error"))
                        else:
                            updated = skill.model_copy(update={
                                "name": edit_name.strip(),
                                "area": edit_area.strip() or skill.area,
                                "description": edit_desc.strip() or None,
                                "prompt": edit_prompt.strip(),
                            })
                            skills_repo.update(updated)
                            del st.session_state["editing_skill_id"]
                            st.rerun()
                    if cancelled:
                        del st.session_state["editing_skill_id"]
                        st.rerun()
                else:
                    st.markdown(f"**{t('settings.description_prefix')}:** {skill.description or '–'}")
                    st.markdown(f"**{t('settings.prompt_prefix')}:**")
                    st.code(skill.prompt, language=None)
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button(t("settings.edit_button"), key=f"edit_{skill.id}", use_container_width=True):
                            st.session_state["editing_skill_id"] = skill.id
                            st.rerun()
                    with col_del:
                        if st.button(t("settings.delete_button"), key=f"del_{skill.id}", type="secondary", use_container_width=True):
                            skills_repo.delete(skill.id)
                            st.success(f"{t('settings.skill_deleted')} '{skill.name}'")
                            st.rerun()

st.divider()

# ------------------------------------------------------------------
# Section: Add skill manually
# ------------------------------------------------------------------

st.subheader(t("settings.add_skill"))

AREA_OPTIONS = ["research", "stock_search", "rebalancing", "portfolio_analysis", t("settings.other_area")]

with st.form("add_skill_form"):
    new_name = st.text_input(t("settings.name_label"), placeholder=t("settings.name_placeholder"))
    area_choice = st.selectbox(t("settings.area_label_required"), AREA_OPTIONS)
    custom_area = ""
    if area_choice == t("settings.other_area"):
        custom_area = st.text_input(t("settings.custom_area_label"), placeholder=t("settings.custom_area_placeholder"))
    new_description = st.text_input(t("settings.description_label"), placeholder=t("settings.description_placeholder"))
    new_prompt = st.text_area(t("settings.prompt_label"), placeholder=t("settings.prompt_placeholder"), height=180)
    save_btn = st.form_submit_button(t("settings.save_button"), use_container_width=True)

if save_btn:
    resolved_area = custom_area.strip() if area_choice == t("settings.other_area") else area_choice
    if not new_name.strip():
        st.error(t("settings.name_required_error"))
    elif area_choice == t("settings.other_area") and not resolved_area:
        st.error(t("settings.area_required_error"))
    elif not new_prompt.strip():
        st.error(t("settings.prompt_required_error"))
    else:
        try:
            skill = Skill(
                name=new_name.strip(),
                area=resolved_area,
                description=new_description.strip() or None,
                prompt=new_prompt.strip(),
            )
            skills_repo.add(skill)
            st.success(f"'{skill.name}' {t('settings.skill_saved')}")
            st.rerun()
        except Exception as exc:
            st.error(f"{t('settings.save_error')}: {exc}")

st.divider()

# ------------------------------------------------------------------
# Section: LLM-generated skill
# ------------------------------------------------------------------

st.subheader(t("settings.generate_header"))

gen_description = st.text_input(
    t("settings.generate_description"),
    placeholder=t("settings.generate_description_placeholder"),
    key="gen_desc",
)
gen_area = st.selectbox(t("settings.generate_area"), AREA_OPTIONS[:-1], key="gen_area")

if st.button(t("settings.generate_button"), key="gen_btn"):
    if not gen_description.strip():
        st.error(t("settings.description_required"))
    else:
        with st.spinner(t("settings.generating")):
            try:
                llm = OllamaProvider(host=config.OLLAMA_HOST, model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX)
                user_msg = (
                    f"Erstelle einen Investment-Analyse-Prompt für folgenden Anwendungsfall: "
                    f"{gen_description.strip()}. Bereich: {gen_area}. "
                    f"Antworte NUR mit dem Prompt-Text selbst, ohne Einleitung oder Erklärung."
                )
                generated = asyncio.run(llm.chat([Message(role=Role.USER, content=user_msg)]))
                st.session_state["gen_result"] = generated
            except Exception as exc:
                st.error(f"{t('settings.ai_error')}: {exc}")

if "gen_result" in st.session_state and st.session_state["gen_result"]:
    st.markdown(f"**{t('settings.generated_label')}:**")
    edited_prompt = st.text_area(
        t("settings.generated_edit_label"),
        value=st.session_state["gen_result"],
        height=200,
        key="gen_edit",
    )
    gen_save_name = st.text_input(t("settings.generated_name_label"), key="gen_save_name")
    gen_save_desc = st.text_input(t("settings.generated_desc_label"), key="gen_save_desc")

    if st.button(t("settings.save_generated"), key="gen_save_btn"):
        if not gen_save_name.strip():
            st.error(t("settings.name_required_gen"))
        elif not edited_prompt.strip():
            st.error(t("settings.prompt_empty_error"))
        else:
            try:
                skill = Skill(
                    name=gen_save_name.strip(),
                    area=gen_area,
                    description=gen_save_desc.strip() or None,
                    prompt=edited_prompt.strip(),
                )
                skills_repo.add(skill)
                st.success(f"'{skill.name}' {t('settings.generated_saved')}")
                del st.session_state["gen_result"]
                st.rerun()
            except Exception as exc:
                st.error(f"{t('settings.save_error')}: {exc}")
