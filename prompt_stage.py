from datetime import date, datetime
from pathlib import Path
import json
import re

from contract_selection import ContractSet, build_contract_set
from excel_writer import save_market_data
from json_validator import validate_response
from manual_completion import apply_manual_records, find_missing_tge_records


PLACEHOLDER_PATTERN = re.compile(r"\{\{[^{}]+\}\}")


def load_prompt_template(template_path: Path) -> str:
    return template_path.read_text(encoding="utf-8")


def build_link_list(base_url: str, dates: list[date], task_label: str) -> str:
    if not dates:
        return "Brak nowych dat do pobrania."
    return "\n\n".join(
        f"ZADANIE {task_label} {index}\n"
        f"- żądana data (do sprawdzenia na stronie): {trading_date.isoformat()}\n"
        f"- otwórz osobno ten URL: "
        f"{base_url}{trading_date.strftime('%d-%m-%Y')}"
        for index, trading_date in enumerate(dates, 1)
    )


def format_contracts(contracts: ContractSet) -> str:
    groups = (
        ("tygodniowe", contracts.weeks),
        ("miesięczne", contracts.months),
        ("kwartalne", contracts.quarters),
        ("roczne", contracts.years),
    )
    return "\n".join(
        f"- {group}: {', '.join(values)}" for group, values in groups
    )


def format_otf_selection(session_date: date) -> str:
    lines = []
    for market, gas in (("gaz", True), ("energia elektryczna", False)):
        contracts = build_contract_set(session_date, gas=gas)
        prefix = "gas_base" if gas else "power_base"
        base_url = (
            "https://tge.pl/gaz-otf?dateShow="
            if gas
            else "https://tge.pl/energia-elektryczna-otf?dateShow="
        )
        lines.append(
            f"{market}: {base_url}{session_date.strftime('%d-%m-%Y')}"
        )
        for group, instruments in (
            ("week", contracts.weeks),
            ("month", contracts.months),
            ("quarter", contracts.quarters),
            ("year", contracts.years),
        ):
            contract_list = ", ".join(
                f"{instrument}={prefix}_{group}_{index}"
                for index, instrument in enumerate(instruments, 1)
            )
            lines.append(f"{group}: {contract_list}")
    return "\n".join(lines)


def build_prompt_replacements(
    source_dates: dict[str, list[date]],
    otf_session_date: date,
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
    retrieved_at: datetime,
) -> dict[str, str]:
    gas_contracts = build_contract_set(otf_session_date, gas=True)
    electricity_contracts = build_contract_set(otf_session_date, gas=False)
    coal_start, coal_end = coal_window
    eua_start, eua_end = eua_window
    return {
        "{{gas_rdn_links}}": build_link_list(
            "https://tge.pl/gaz-rdn?dateShow=", source_dates["gas_rdn"], "GAZ RDN"
        ),
        "{{electricity_rdn_links}}": build_link_list(
            "https://tge.pl/energia-elektryczna-rdn?dateShow=",
            source_dates["electricity_rdn"],
            "ENERGIA RDN",
        ),
        "{{gas_otf_url}}": (
            "https://tge.pl/gaz-otf?dateShow="
            f"{otf_session_date.strftime('%d-%m-%Y')}"
        ),
        "{{electricity_otf_url}}": (
            "https://tge.pl/energia-elektryczna-otf?dateShow="
            f"{otf_session_date.strftime('%d-%m-%Y')}"
        ),
        "{{otf_session_date}}": otf_session_date.isoformat(),
        "{{otf_selection}}": format_otf_selection(otf_session_date),
        "{{gas_contracts}}": format_contracts(gas_contracts),
        "{{electricity_contracts}}": format_contracts(electricity_contracts),
        "{{coal_start_date}}": coal_start.isoformat(),
        "{{coal_end_date}}": coal_end.isoformat(),
        "{{eua_start_date}}": eua_start.isoformat(),
        "{{eua_end_date}}": eua_end.isoformat(),
        "{{retrieved_at}}": retrieved_at.isoformat(),
    }


def build_prompt(
    template: str,
    source_dates: dict[str, list[date]],
    otf_session_date: date,
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
    retrieved_at: datetime | None = None,
) -> str:
    replacements = build_prompt_replacements(
        source_dates=source_dates,
        otf_session_date=otf_session_date,
        coal_window=coal_window,
        eua_window=eua_window,
        retrieved_at=retrieved_at or datetime.now().astimezone(),
    )
    prompt = template
    for placeholder, replacement in replacements.items():
        prompt = prompt.replace(placeholder, replacement)
    unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(prompt)))
    if unresolved:
        raise ValueError(
            "W szablonie pozostały niezastąpione znaczniki: "
            + ", ".join(unresolved)
        )
    return prompt


def show_prompt_page(workbook_path: Path) -> None:
    import streamlit as st

    st.title("Pobierz dane ze źródeł")
    source_dates = st.session_state["confirmed_source_dates"]
    otf_session_date = st.session_state["otf_session_date"]
    coal_window = st.session_state["coal_window"]
    eua_window = st.session_state["eua_window"]

    st.subheader("1. Otwórz kilka sesji AI")
    st.markdown(
        "Otwórz [https://chatgpt.com/](https://chatgpt.com/) w "
        "**trybie incognito/prywatnym** "
        "i upewnij się, że nie jesteś zalogowany. Przygotuj **3–5 osobnych "
        "rozmów**. Dzięki temu porównasz niezależne odpowiedzi."
    )
    st.subheader("2–3. Uruchom prompt i poczekaj na odpowiedzi")
    st.markdown(
        "Skopiuj prompt z pola poniżej i wklej go do każdej przygotowanej "
        "rozmowy. Poczekaj, aż wszystkie sesje zakończą pracę."
    )
    with st.expander("Zakres danych przygotowany przez aplikację"):
        for source, dates in source_dates.items():
            label = {
                "gas_rdn": "Ceny dzienne gazu",
                "electricity_rdn": "Ceny dzienne energii",
                "gas_otf": "Kontrakty terminowe na gaz",
                "electricity_otf": "Kontrakty terminowe na energię",
            }[source]
            if source.endswith("_otf"):
                st.write(label, otf_session_date.isoformat())
            else:
                st.write(label, [value.isoformat() for value in dates])
        st.write("Wybrana data sesji OTF")
        st.write(otf_session_date.isoformat())
        st.write("Kontrakty gazowe dla wybranej daty")
        st.code(format_contracts(build_contract_set(otf_session_date, gas=True)))
        st.write("Kontrakty energetyczne dla wybranej daty")
        st.code(
            format_contracts(build_contract_set(otf_session_date, gas=False))
        )
        st.write("Historia węgla", f"{coal_window[0]} – {coal_window[1]}")
        st.write("Historia uprawnień do emisji EUA", f"{eua_window[0]} – {eua_window[1]}")

    try:
        prompt = build_prompt(
            st.session_state["prompt_template"],
            source_dates=source_dates,
            otf_session_date=otf_session_date,
            coal_window=coal_window,
            eua_window=eua_window,
        )
    except (KeyError, ValueError) as error:
        st.error(f"Nie udało się zbudować promptu: {error}")
        return

    st.subheader("Prompt do skopiowania")
    st.caption(
        "Skopiuj cały tekst przyciskiem kopiowania w rogu pola. Użyj tego "
        "samego promptu w każdej rozmowie."
    )
    st.code(prompt, language=None, height=450)

    st.subheader("4–6. Wybierz odpowiedź i wklej ją tutaj")
    st.caption(
        "Sprawdź pole `errors` w każdej odpowiedzi. Najpierw wybierz tę z "
        "pustą listą `errors` (`[]`). Jeśli wszystkie mają błędy, wybierz "
        "odpowiedź z najmniejszą liczbą wpisów w `errors`. Skopiuj ją w całości "
        "i wklej poniżej."
    )
    with st.form("response_form"):
        response = st.text_area(
            "Pełna odpowiedź",
            value=st.session_state.get("response", ""),
            height=300,
        )
        validate_json = st.form_submit_button("Sprawdź odpowiedź", type="primary")
    if validate_json:
        st.session_state["data_saved"] = False
        st.session_state.pop("validation_report", None)
        st.session_state.pop("parsed_response", None)
        st.session_state.pop("validated_payload", None)
        st.session_state.pop("validated_sections", None)
        if not response.strip():
            st.warning("Wklej odpowiedź przed jej zapisaniem.")
        else:
            st.session_state["response"] = response
            report = validate_response(
                response,
                source_dates=source_dates,
                otf_session_date=otf_session_date,
                coal_window=coal_window,
                eua_window=eua_window,
            )
            st.session_state["validation_report"] = report
            if report.data is not None:
                st.session_state["parsed_response"] = report.data
            else:
                st.session_state.pop("parsed_response", None)
            if report.is_structurally_valid:
                st.session_state["validated_payload"] = report.data
                st.session_state["validated_sections"] = {
                    section: valid
                    for section, valid in report.section_validity.items()
                }
            else:
                st.session_state.pop("validated_payload", None)
                st.session_state.pop("validated_sections", None)
            if report.is_structurally_valid:
                st.session_state["page"] = "review"
                st.rerun()

    report = st.session_state.get("validation_report")
    if report is not None:
        st.subheader("Wynik sprawdzenia")
        global_errors = [
            issue
            for issue in report.issues
            if issue.section == "global" and issue.severity == "error"
        ]
        if report.is_structurally_valid:
            st.success(
                "Odpowiedź ma poprawny format. Otwieram teraz kontrolę "
                "kompletności danych."
            )
        else:
            st.error(
                "Nie udało się odczytać odpowiedzi. Popraw wskazane problemy "
                "lub wklej pełną odpowiedź ponownie."
            )
        st.subheader("Czy są wszystkie potrzebne dane?")
        valid_count = sum(report.section_validity.values())
        if report.is_valid:
            st.success(
                f"Wszystkie sekcje są kompletne: {valid_count}/"
                f"{len(report.section_validity)}."
            )
        elif report.is_structurally_valid:
            st.warning(
                f"Kompletne sekcje: {valid_count}/{len(report.section_validity)}. "
                "Braki nie unieważniają struktury JSON-a — uzupełnij je poniżej."
            )
        st.dataframe(
            [
                {
                    "Rodzaj danych": {
                        "gas.day_ahead": "Ceny dzienne gazu",
                        "gas.futures": "Kontrakty terminowe na gaz",
                        "electricity.day_ahead": "Ceny dzienne energii",
                        "electricity.futures": "Kontrakty terminowe na energię",
                        "coal.futures": "Historia węgla",
                        "emissions.futures": "Historia uprawnień EUA",
                    }.get(section, section),
                    "Stan": "gotowe" if valid else "wymaga sprawdzenia",
                }
                for section, valid in report.section_validity.items()
            ],
            hide_index=True,
            width="stretch",
        )
        if global_errors:
            st.error(
                f"Pozostało {len(global_errors)} problemów z odczytem. "
                "Sprawdź szczegóły poniżej."
            )
        if report.issues:
            with st.expander("Szczegóły problemów do poprawy"):
                st.dataframe(
                    [
                        {
                            "Rodzaj danych": issue.section,
                            "Miejsce": issue.path,
                            "Szczegóły": issue.message,
                        }
                        for issue in report.issues
                    ],
                    hide_index=True,
                    width="stretch",
                )

        if report.is_structurally_valid and report.data is not None:
            missing_records = find_missing_tge_records(
                report.data,
                source_dates,
                (
                    date.fromisoformat(report.data["otf_session_date"])
                    if isinstance(report.data.get("otf_session_date"), str)
                    else None
                ),
            )
            if missing_records:
                st.subheader("Uzupełnianie brakujących danych TGE")
                st.write(
                    "Każdy brak zawiera dokładny link, datę i instrument. "
                    "Wpisz wartości ze źródła i potwierdź rekord. Puste pole "
                    "oznacza potwierdzony brak wartości (null)."
                )
                completed = []
                with st.form("manual_completion_form"):
                    for index, missing in enumerate(missing_records):
                        st.markdown(
                            f"**{missing.instrument} — {missing.trading_date}**  "
                            f"[{missing.source_url}]({missing.source_url})"
                        )
                        columns = st.columns(len(missing.value_fields) + 1)
                        values = {}
                        for column, field in zip(columns, missing.value_fields):
                            values[field] = column.number_input(
                                field,
                                value=None,
                                key=f"manual_{index}_{field}",
                            )
                        confirmed = columns[-1].checkbox(
                            "Potwierdzono", key=f"manual_{index}_confirmed"
                        )
                        completed.append((missing, values, confirmed))
                    apply_manual = st.form_submit_button(
                        "Zastosuj ręczne uzupełnienia", type="primary"
                    )
                if apply_manual:
                    if not all(item[2] for item in completed):
                        st.error(
                            "Potwierdź wszystkie brakujące rekordy przed ponowną walidacją."
                        )
                    else:
                        updated = apply_manual_records(
                            report.data,
                            [(missing, values) for missing, values, _ in completed],
                        )
                        updated_text = json.dumps(updated, ensure_ascii=False)
                        updated_report = validate_response(
                            updated_text,
                            source_dates=source_dates,
                            otf_session_date=otf_session_date,
                            coal_window=coal_window,
                            eua_window=eua_window,
                        )
                        st.session_state["response"] = updated_text
                        st.session_state["validation_report"] = updated_report
                        st.session_state["parsed_response"] = updated
                        if updated_report.is_structurally_valid:
                            st.session_state["validated_payload"] = updated
                            st.session_state["validated_sections"] = dict(
                                updated_report.section_validity
                            )
                        st.rerun()

        st.subheader("Zapis danych")
        if report.is_valid and report.data is not None:
            st.write(
                "Wszystkie sekcje są kompletne. Zapis zaktualizuje RDN i OTF "
                "po kluczu data + data_id oraz bezpiecznie zastąpi okna węgla i EUA."
            )
            if st.button("Zapisz dane do DataMaster.xlsx", type="primary"):
                try:
                    save_market_data(
                        workbook_path,
                        report.data,
                        coal_window,
                        eua_window,
                    )
                except (OSError, ValueError, KeyError) as error:
                    st.error(f"Nie udało się zapisać danych: {error}")
                else:
                    st.session_state["data_saved"] = True
                    st.session_state.pop("date_plan", None)
                    st.success("Dane zostały zapisane w DataMaster.xlsx.")
        else:
            invalid_sections = [
                section
                for section, valid in report.section_validity.items()
                if not valid
            ]
            reasons = []
            if invalid_sections:
                reasons.append("błędne sekcje: " + ", ".join(invalid_sections))
            if global_errors:
                reasons.append(f"błędy globalne: {len(global_errors)}")
            metadata_errors = [
                issue
                for issue in report.issues
                if issue.section == "metadata" and issue.severity == "error"
            ]
            if metadata_errors:
                reasons.append(f"niespójne metadane: {len(metadata_errors)}")
            if report.data is None:
                reasons.append("nie odczytano obiektu JSON")
            st.warning(
                "Zapis jest obecnie zablokowany — "
                + ("; ".join(reasons) if reasons else "walidacja nie jest kompletna")
                + "."
            )
            st.button(
                "Zapisz dane do DataMaster.xlsx",
                type="primary",
                disabled=True,
                key="save_disabled",
            )

    if st.button("Wróć do weryfikacji dat"):
        st.session_state.pop("holiday_date_table", None)
        st.session_state["page"] = "dates"
        st.rerun()
