# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

Streamlit 기반 쇼핑 리스트 웹 앱(아이템 추가/수정/삭제/체크, 진행 바, 체크 항목 일괄 삭제). UI는 한국어, 앱 코드는 단일 파일 `app.py`. 요구사항 기준은 `PRD.md`, 단계별 개발 프롬프트는 `PROMPTS.md`. 아직 배포 전이며 대상은 Streamlit Community Cloud. 의존성은 `streamlit`, `streamlit-js-eval`.

## 명령어

```bash
pip install -r requirements.txt
streamlit run app.py                       # 로컬 실행 (http://localhost:8501)
python -m pytest test_logic.py -q          # 단위 테스트
python -m pytest test_logic.py -k toggle   # 단일 테스트
python tests/e2e_check.py                  # Playwright E2E (앱이 8501에서 실행 중이어야 함, APP_URL로 변경 가능)
```

- E2E는 `pip install playwright pytest` 후 `python -m playwright install chromium`이 필요하다. 스크린샷은 `tests/screenshots/`(gitignore)에 저장된다.
- Windows 콘솔(cp949)에서 E2E 출력의 이모지 때문에 `UnicodeEncodeError`가 나므로 `PYTHONIOENCODING=utf-8`을 지정해 실행한다.
- 린터/빌드 설정은 없다.

## 아키텍처

- **로직/UI 분리**: 조작 함수(`add_item`, `update_item`, `delete_item`, `toggle_item`, `clear_checked`, `progress`)는 `state`(dict 또는 `st.session_state`)를 첫 인자로 받는 순수 함수다. 그래서 `test_logic.py`가 Streamlit 없이 테스트한다. UI는 `main()` 안에서만 실행되고, `cb_*` 콜백이 이 함수들을 `st.session_state`로 호출한다.
- **상태**: `st.session_state`의 `items`(list of `{id: uuid4 hex, name, qty, checked}`)와 `editing_id`(수정 중인 아이템 id 또는 None). 수정은 한 번에 하나만 가능하고, 삭제 시 `editing_id`를 정리해야 한다.
- **영속성**: 서버가 아닌 브라우저 `localStorage`(키 `shopping_list_v1`)에 JSON으로 저장한다(`load_from_browser` / `save_to_browser`, `streamlit-js-eval`). 첫 실행에서는 브라우저 응답이 올 때까지 `st.stop()`으로 대기하고, 저장은 `saved_json`과 달라졌을 때만 한다. 불러온 데이터는 `parse_items`로 검증한다. 사용자 브라우저별 저장이므로 기기 간 동기화는 없다. Streamlit Cloud는 서버 파일이 비영구적이고 사용자 간에 공유되므로 서버 JSON 파일 저장은 쓰지 않는다. 동기화가 필요하면 외부 DB로 교체하며, 이때 조작 함수와 저장 함수만 바꾸면 된다.
- **위젯 key**: 모든 아이템 위젯 key에 아이템 `id`를 넣는다(`chk_{id}` 등). 동일 이름 아이템 간 충돌 방지.

## 함정 (이미 겪은 문제)

- 추가 폼의 입력창 초기화는 `st.form(clear_on_submit=True)`에 맡긴다. 콜백에서 위젯 key에 직접 값을 대입하면, 수량에 범위 밖 값을 넣은 뒤 이전 이름이 중복 추가되는 버그가 생겼다.
- 체크 항목은 마크다운 취소선(`~~이름~~`)으로 표시하므로 `md_escape()`로 사용자 입력을 이스케이프한다. 백슬래시 이스케이프로는 URL/이메일 자동 링크가 막히지 않아 제로폭 공백(U+200B)을 삽입한다.
- 모바일에서 컬럼이 세로로 쌓이지 않도록 CSS로 `nowrap`을 강제하고, "Press Enter to submit form" 안내는 입력창을 가려서 CSS로 숨겼다(Enter 제출은 그대로 동작). 레이아웃을 바꿀 때는 폭 375px에서 버튼이 한 줄에 남는지 확인한다.
- 알려진 한계: 수량에 범위 밖 값(0, 1000 이상)을 넣고 추가하면 Streamlit 프론트가 제출을 거부해 아이템이 조용히 추가되지 않는다.
