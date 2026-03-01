export const PAGES = {
  HOME: "home",
  SAMPLE: "sample",
  AGENT: "agent",
};

export const PAGE_TEXT = {
  home: {
    title: "Demand Forecast + Inventory Optimizer",
    subtitle:
      "Choose a dedicated workflow page to avoid mode/config confusion.",
  },
  sample: {
    title: "Sample / Deterministic UI",
    subtitle:
      "Forecast using notebook output, then optimize deterministic allocation.",
  },
  agent: {
    title: "Agent Pipeline UI",
    subtitle:
      "Provide sales/weather/seasonal APIs, then trigger forecast + allocation in one action.",
  },
};

export const HOME_CARDS = [
  {
    page: PAGES.SAMPLE,
    title: "Sample / Deterministic",
    description: "Notebook forecast + deterministic allocation flow.",
    buttonLabel: "Open Sample UI",
  },
  {
    page: PAGES.AGENT,
    title: "Agent Pipeline",
    description: "Specialist signals + final forecast + optimization pipeline.",
    buttonLabel: "Open Agent UI",
  },
];
