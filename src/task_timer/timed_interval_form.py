"""Standalone draft input fields for genuine timed intervals; no record access."""

from __future__ import annotations

from datetime import date, tzinfo
from tkinter import StringVar, ttk

from .work_entry_inputs import local_minute_candidates, resolve_timed_interval_input


class TimedIntervalInputFrame(ttk.Frame):
    """Interpret explicit local inputs without saving or loading work records."""

    def __init__(
        self, parent, *, local_timezone: tzinfo, start_date: date, end_date: date,
        start_time: str = "", end_time: str = "",
    ) -> None:
        if type(start_date) is not date or type(end_date) is not date:
            raise ValueError("Initial endpoint dates must be exact date objects")
        if not isinstance(start_time, str) or not isinstance(end_time, str):
            raise ValueError("Initial clock inputs must be strings")
        if not isinstance(local_timezone, tzinfo):
            raise ValueError("An explicit timezone object is required")
        super().__init__(parent)
        self.local_timezone = local_timezone
        self.error_var = StringVar(master=self, value="")
        self._choices = {"start": {}, "end": {}}
        zone_label = getattr(local_timezone, "key", None) or str(local_timezone)
        self.timezone_label = ttk.Label(self, text=f"Timezone: {zone_label}")
        self.timezone_label.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))

        for endpoint, day, clock, row in (("start", start_date, start_time, 1), ("end", end_date, end_time, 3)):
            date_var = StringVar(master=self, value=day.isoformat())
            time_var = StringVar(master=self, value=clock)
            occurrence_var = StringVar(master=self, value="")
            error_var = StringVar(master=self, value="")
            for name, variable in (("date", date_var), ("time", time_var),
                                   ("occurrence", occurrence_var), ("error", error_var)):
                setattr(self, f"{endpoint}_{name}_var", variable)
            ttk.Label(self, text=f"{endpoint.title()} date").grid(row=row, column=0, sticky="w", padx=(0, 4))
            date_entry = ttk.Entry(self, textvariable=date_var, width=12)
            date_entry.grid(row=row, column=1, sticky="ew", padx=(0, 8))
            ttk.Label(self, text=f"{endpoint.title()} time").grid(row=row, column=2, sticky="w", padx=(0, 4))
            time_entry = ttk.Entry(self, textvariable=time_var, width=12)
            time_entry.grid(row=row, column=3, sticky="ew", padx=(0, 8))
            selector = ttk.Combobox(self, textvariable=occurrence_var, state="readonly", width=30)
            selector.grid(row=row, column=4, sticky="ew")
            selector.bind("<<ComboboxSelected>>", lambda _event, key=endpoint: self._selection_changed(key))
            setattr(self, f"{endpoint}_date_entry", date_entry)
            setattr(self, f"{endpoint}_time_entry", time_entry)
            setattr(self, f"{endpoint}_occurrence_selector", selector)
            ttk.Label(self, textvariable=error_var, foreground="#b00020", wraplength=600).grid(
                row=row + 1, column=0, columnspan=5, sticky="w")
            for variable in (date_var, time_var):
                variable.trace_add("write", lambda *_args, key=endpoint: self._endpoint_changed(key))
        ttk.Label(self, textvariable=self.error_var, foreground="#b00020", wraplength=600).grid(
            row=5, column=0, columnspan=5, sticky="w")
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(3, weight=1)
        self._refresh_endpoint("start")
        self._refresh_endpoint("end")

    def _read_date(self, endpoint):
        text = getattr(self, f"{endpoint}_date_var").get().strip()
        try:
            day = date.fromisoformat(text)
            if day.isoformat() != text:
                raise ValueError
        except ValueError:
            raise ValueError(f"{endpoint.title()} date must be YYYY-MM-DD") from None
        return day

    def _choice_label(self, candidate, name):
        local = candidate.astimezone(self.local_timezone)
        offset = int(local.utcoffset().total_seconds())
        hours, remainder = divmod(abs(offset), 3600)
        minutes, seconds = divmod(remainder, 60)
        suffix = f":{seconds:02d}" if seconds else ""
        return f"{name} {local:%H:%M} (UTC{'+' if offset >= 0 else '-'}{hours:02d}:{minutes:02d}{suffix})"

    def _refresh_endpoint(self, endpoint):
        selector = getattr(self, f"{endpoint}_occurrence_selector")
        selected = getattr(self, f"{endpoint}_occurrence_var")
        error = getattr(self, f"{endpoint}_error_var")
        try:
            candidates = local_minute_candidates(
                self._read_date(endpoint), getattr(self, f"{endpoint}_time_var").get(), self.local_timezone)
            if not candidates:
                raise ValueError("Local time does not exist in the supplied timezone")
            choices = ({self._choice_label(candidate, label): value
                        for candidate, label, value in zip(candidates, ("First", "Second"), ("first", "second"))}
                       if len(candidates) == 2 else {})
        except ValueError as exc:
            choices = {}
            error.set(f"{endpoint.title()}: {exc}")
        else:
            error.set(f"{endpoint.title()}: Select first or second occurrence"
                      if choices and selected.get() not in choices else "")
        self._choices[endpoint] = choices
        selector.configure(values=tuple(choices), state="readonly" if choices else "disabled")
        if selected.get() not in choices:
            selected.set("")
        if choices:
            selector.grid()
        else:
            selector.grid_remove()

    def _endpoint_changed(self, endpoint):
        getattr(self, f"{endpoint}_occurrence_var").set("")
        self.error_var.set("")
        self._refresh_endpoint(endpoint)

    def _selection_changed(self, endpoint):
        self.error_var.set("")
        self._refresh_endpoint(endpoint)

    def resolve_input(self):
        """Revalidate the current draft; retain invalid values for correction."""
        self._refresh_endpoint("start")
        self._refresh_endpoint("end")
        try:
            result = resolve_timed_interval_input(
                self._read_date("start"), self.start_time_var.get(),
                self._read_date("end"), self.end_time_var.get(), self.local_timezone,
                start_occurrence=self._choices["start"].get(self.start_occurrence_var.get()),
                end_occurrence=self._choices["end"].get(self.end_occurrence_var.get()),
            )
        except ValueError as exc:
            message = "; ".join(filter(None, (self.start_error_var.get(), self.end_error_var.get())))
            message = message or f"Interval: {exc}"
            self.error_var.set(message)
            raise ValueError(message) from exc
        self.error_var.set("")
        self.start_error_var.set("")
        self.end_error_var.set("")
        return result
