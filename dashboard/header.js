(() => {
  const dateElement = document.getElementById("report-date");

  if (!(dateElement instanceof HTMLTimeElement)) {
    return;
  }

  const now = new Date();
  const dateParts = new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Warsaw",
    year: "numeric"
  }).formatToParts(now);
  const dateValues = Object.fromEntries(
    dateParts
      .filter(({ type }) => type !== "literal")
      .map(({ type, value }) => [type, value])
  );
  const isoDate = `${dateValues.year}-${dateValues.month}-${dateValues.day}`;
  const displayDate = `${dateValues.day}.${dateValues.month}.${dateValues.year}`;

  dateElement.dateTime = isoDate;
  dateElement.textContent = displayDate;
})();
