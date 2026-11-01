import React from 'react';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';
import { GuideIcon } from './brand/Marks';

/** A consistent reading entrance for guides, without changing Docusaurus navigation. */
export function DocHero({ title, eyebrow, icon = 'spark', facts = [], children }) {
  return (
    <header className={`sibyl-doc-hero sibyl-doc-hero-${icon}`}>
      <div className="sibyl-doc-hero-art" aria-hidden="true">
        <GuideIcon name={icon} />
      </div>
      <span className="sibyl-doc-eyebrow">
        <GuideIcon name={icon} />
        {eyebrow}
      </span>
      <Heading as="h1">{title}</Heading>
      <div className="sibyl-doc-lead">{children}</div>
      {facts.length > 0 && (
        <ul className="sibyl-doc-facts">
          {facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
      )}
    </header>
  );
}

/** Short, real reading paths; every card links to a document or an existing section. */
export function DocCards({ items }) {
  return (
    <div className="sibyl-reading-paths">
      {items.map((item) => (
        <Link className="sibyl-reading-card" to={item.to} key={item.title}>
          <GuideIcon name={item.icon || 'arrow'} />
          <strong>{item.title}</strong>
          <span>{item.text}</span>
          <GuideIcon name="arrow" className="sibyl-reading-arrow" />
        </Link>
      ))}
    </div>
  );
}

/** The actual technical-bias weights, illustrated without inventing a market reading. */
export function BiasWeights() {
  const weights = [
    ['EMA alignment', 25],
    ['Trend', 20],
    ['MACD', 20],
    ['RSI', 20],
    ['Volume', 15],
  ];
  return (
    <figure className="sibyl-weight-figure">
      <figcaption>
        <span>Inside the score</span>
        <strong>Five readings. One weighted view.</strong>
      </figcaption>
      <div className="sibyl-weight-bar" aria-hidden="true">
        {weights.map(([name, weight], index) => (
          <span key={name} style={{ flex: weight }} className={`sibyl-weight-${index}`}>
            {weight}%
          </span>
        ))}
      </div>
      <ul>
        {weights.map(([name, weight], index) => (
          <li key={name}>
            <i className={`sibyl-weight-${index}`} />
            <span>{name}</span>
            <strong>{weight}%</strong>
          </li>
        ))}
      </ul>
      <p>Fixed weights describe technical alignment. They are not probabilities or a forecast.</p>
    </figure>
  );
}
