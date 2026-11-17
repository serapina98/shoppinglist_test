import json
import re
import uuid

import streamlit as st
from streamlit_js_eval import streamlit_js_eval

STORAGE_KEY = "shopping_list_v1"  # 브라우저 localStorage 키

# ---------------------------------------------------------------------------
# 데이터 조작 함수 (UI와 분리). state는 st.session_state 또는 dict.
# 저장소를 교체할 때 이 함수들만 바꾸면 된다.
# ---------------------------------------------------------------------------


def init_state(state):
    state.setdefault("items", [])
    state.setdefault("editing_id", None)


def _clean_name(name):
    return " ".join((name or "").split())


def add_item(state, name, qty=1):
    """아이템 추가. 이름이 비어 있으면 추가하지 않고 False 반환."""
    name = _clean_name(name)
    if not name:
        return False
    state["items"].append(
        {"id": uuid.uuid4().hex, "name": name, "qty": max(1, int(qty)), "checked": False}
    )
    return True


def update_item(state, item_id, name, qty):
    """아이템 수정. 이름이 비어 있거나 대상이 없으면 False 반환."""
    name = _clean_name(name)
    if not name:
        return False
    for item in state["items"]:
        if item["id"] == item_id:
            item["name"] = name
            item["qty"] = max(1, int(qty))
            return True
    return False


def delete_item(state, item_id):
    state["items"] = [i for i in state["items"] if i["id"] != item_id]
    if state.get("editing_id") == item_id:
        state["editing_id"] = None


def toggle_item(state, item_id, checked=None):
    for item in state["items"]:
        if item["id"] == item_id:
            item["checked"] = (not item["checked"]) if checked is None else bool(checked)
            return


def clear_checked(state):
    state["items"] = [i for i in state["items"] if not i["checked"]]
    editing = state.get("editing_id")
    if editing and not any(i["id"] == editing for i in state["items"]):
        state["editing_id"] = None


def progress(state):
    total = len(state["items"])
    done = sum(1 for i in state["items"] if i["checked"])
    return done, total


def parse_items(raw):
    """localStorage 문자열 → 유효한 아이템 목록. 손상된 데이터는 걸러낸다."""
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    items = []
    if isinstance(data, list):
        for d in data:
            if isinstance(d, dict) and isinstance(d.get("name"), str) and d["name"].strip():
                try:
                    qty = max(1, int(d.get("qty", 1)))
                except (TypeError, ValueError):
                    qty = 1
                items.append(
                    {
                        "id": str(d.get("id") or uuid.uuid4().hex),
                        "name": d["name"],
                        "qty": qty,
                        "checked": bool(d.get("checked", False)),
                    }
                )
    return items


def dump_items(items):
    return json.dumps(items, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# 브라우저 저장소 (새로고침 후에도 유지). 사용자별 브라우저 localStorage에 저장한다.
# ---------------------------------------------------------------------------


def load_from_browser():
    """첫 실행 시 localStorage에서 목록을 불러온다. 값이 도착하기 전이면 False."""
    s = st.session_state
    if s.get("storage_loaded"):
        return True
    raw = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}') || ''", key="ls_load")
    if raw is None:  # 브라우저 응답 대기 중
        return False
    s["items"] = parse_items(raw)
    s["saved_json"] = dump_items(s["items"])
    s["storage_loaded"] = True
    return True


def save_to_browser():
    """목록이 바뀌었을 때만 localStorage에 기록한다."""
    s = st.session_state
    current = dump_items(s["items"])
    if current == s.get("saved_json"):
        return
    s["save_n"] = s.get("save_n", 0) + 1
    streamlit_js_eval(
        js_expressions=f"localStorage.setItem('{STORAGE_KEY}', {json.dumps(current)})",
        key=f"ls_save_{s['save_n']}",
    )
    s["saved_json"] = current


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!~|<>$&:/@])")

CSS = """
<style>
.block-container { max-width: 640px; padding-top: 2rem; }
/* 모바일에서도 한 줄 유지 */
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.4rem; }
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width: 0 !important; }
div[data-testid="stForm"] { border: none; padding: 0; }
.stButton > button, div[data-testid="stFormSubmitButton"] > button { padding: 0.25rem 0.5rem; min-height: 2.5rem; white-space: nowrap; }
div[data-testid="stFormSubmitButton"] button p, .stButton button p { white-space: nowrap; }
/* "Press Enter to submit form" 안내가 입력창을 가리지 않도록 숨김 (Enter 제출은 그대로 동작) */
div[data-testid="InputInstructions"] { display: none; }
.empty-box { text-align: center; color: #8a8f98; padding: 2rem 0; border: 1px dashed #c8ccd2; border-radius: 0.5rem; }
.item-name { overflow-wrap: anywhere; }
</style>
"""


def md_escape(text):
    """사용자 입력이 마크다운 서식을 깨뜨리지 않도록 이스케이프."""
    # URL/이메일 자동 링크는 백슬래시로 막히지 않으므로 제로폭 공백으로 끊는다.
    text = re.sub(r"(?i)(https?|ftp):(?=//)", lambda m: m.group(1) + ":​", text)
    text = re.sub(r"(?i)\bwww\.", "www​.", text)
    text = text.replace("@", "​@")
    return _MD_SPECIAL.sub(r"\\\1", text)


def _label(item):
    name = md_escape(item["name"])
    qty = f" ×{item['qty']}" if item["qty"] > 1 else ""
    return f"~~{name}{qty}~~" if item["checked"] else f"{name}{qty}"


# --- 콜백 ---------------------------------------------------------------


def cb_add():
    s = st.session_state
    # 입력창 초기화는 st.form(clear_on_submit=True)가 처리한다.
    s["add_warning"] = not add_item(s, s.get("new_name", ""), s.get("new_qty", 1))


def cb_toggle(item_id):
    toggle_item(st.session_state, item_id, st.session_state.get(f"chk_{item_id}"))


def cb_delete(item_id):
    delete_item(st.session_state, item_id)


def cb_clear_checked():
    clear_checked(st.session_state)


def cb_start_edit(item_id):
    s = st.session_state
    item = next(i for i in s["items"] if i["id"] == item_id)
    s["editing_id"] = item_id
    s[f"edit_name_{item_id}"] = item["name"]
    s[f"edit_qty_{item_id}"] = item["qty"]
    s["edit_warning"] = False


def cb_save_edit(item_id):
    s = st.session_state
    if update_item(s, item_id, s.get(f"edit_name_{item_id}", ""), s.get(f"edit_qty_{item_id}", 1)):
        s["editing_id"] = None
        s["edit_warning"] = False
    else:
        s["edit_warning"] = True


def cb_cancel_edit():
    st.session_state["editing_id"] = None
    st.session_state["edit_warning"] = False


# --- 화면 ---------------------------------------------------------------


def render_add_form():
    with st.form("add_form", clear_on_submit=True, border=False):
        c_name, c_qty, c_btn = st.columns([5, 2, 3], vertical_alignment="bottom")
        c_name.text_input("아이템", key="new_name", placeholder="예: 우유", label_visibility="collapsed")
        c_qty.number_input("수량", min_value=1, max_value=999, value=1, step=1, key="new_qty", label_visibility="collapsed")
        c_btn.form_submit_button("➕ 추가", on_click=cb_add, use_container_width=True)
    if st.session_state.get("add_warning"):
        st.warning("아이템 이름을 입력해 주세요.")


def render_progress():
    done, total = progress(st.session_state)
    st.markdown(f"**{done} / {total} 완료**")
    st.progress(done / total if total else 0.0)


def render_item(item):
    iid = item["id"]
    if st.session_state["editing_id"] == iid:
        c_name, c_qty, c_save, c_cancel = st.columns([5, 2, 1, 1], vertical_alignment="center")
        c_name.text_input("이름", key=f"edit_name_{iid}", label_visibility="collapsed")
        c_qty.number_input("수량", min_value=1, max_value=999, step=1, key=f"edit_qty_{iid}", label_visibility="collapsed")
        c_save.button("✅", key=f"save_{iid}", on_click=cb_save_edit, args=(iid,), help="저장")
        c_cancel.button("❌", key=f"cancel_{iid}", on_click=cb_cancel_edit, help="취소")
        if st.session_state.get("edit_warning"):
            st.warning("이름을 입력해 주세요.")
        return

    c_chk, c_edit, c_del = st.columns([8, 1, 1], vertical_alignment="center")
    c_chk.checkbox(
        _label(item),
        value=item["checked"],
        key=f"chk_{iid}",
        on_change=cb_toggle,
        args=(iid,),
    )
    c_edit.button("✏️", key=f"edit_{iid}", on_click=cb_start_edit, args=(iid,), help="수정")
    c_del.button("🗑️", key=f"del_{iid}", on_click=cb_delete, args=(iid,), help="삭제")


def render_list():
    items = st.session_state["items"]
    if not items:
        st.markdown('<div class="empty-box">아직 추가된 아이템이 없어요 🛍️</div>', unsafe_allow_html=True)
        return
    for item in items:
        render_item(item)
    has_checked = any(i["checked"] for i in items)
    st.button(
        "체크된 항목 모두 삭제",
        key="clear_checked",
        on_click=cb_clear_checked,
        disabled=not has_checked,
        use_container_width=True,
    )


def main():
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    init_state(st.session_state)
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🛒 쇼핑 리스트")
    if not load_from_browser():
        st.caption("목록을 불러오는 중…")
        st.stop()
    render_add_form()
    st.divider()
    render_progress()
    render_list()
    st.caption("목록은 이 브라우저에 저장되어 새로고침해도 유지됩니다.")
    save_to_browser()


if __name__ == "__main__":
    main()
