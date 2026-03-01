import React from "react";
import { HOME_CARDS, PAGE_TEXT } from "../constants/pageConfig.js";
import PageHeader from "./PageHeader.jsx";

export default function HomePage({ summary, inbound, onNavigate }) {
  return (
    <div className="page">
      <PageHeader
        title={PAGE_TEXT.home.title}
        subtitle={PAGE_TEXT.home.subtitle}
        summary={summary}
        inbound={inbound}
      />
      <div
        className="grid-two"
        style={{ gridTemplateColumns: `repeat(${HOME_CARDS.length}, minmax(0, 1fr))` }}
      >
        {HOME_CARDS.map((card) => (
          <div className="panel" key={card.page}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>{card.title}</div>
            <div className="muted" style={{ marginBottom: 12 }}>
              {card.description}
            </div>
            <button className="button-primary" onClick={() => onNavigate(card.page)}>
              {card.buttonLabel}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
