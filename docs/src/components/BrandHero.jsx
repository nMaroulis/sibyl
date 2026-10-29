import React from 'react';
import Link from '@docusaurus/Link';

export default function BrandHero() {
  return (
    <div className="sibyl-doc-home">
      <div className="sibyl-doc-hero">
        <span className="doc-welcome-badge">SIBYL v2.1.0 · THE WORKSPACE GUIDE</span>
        <h1>Sibyl, explained.</h1>
        <p>
          Your accounts, your research, your AI team.
          <br />
          Everything you need to make the workspace your own.
        </p>
        <Link className="sibyl-doc-button" to="/getting-started/installation">
          Get started <span>↗</span>
        </Link>
      </div>
      <div className="sibyl-doc-paths">
        <Link to="/guides/account">
          <span className="doc-card-index">01</span>
          <strong>Your accounts</strong>
          <p>Connected accounts, balances, and a clear view of your assets.</p>
          <b>↗</b>
        </Link>
        <Link to="/guides/sibyl">
          <span className="doc-card-index">02</span>
          <strong>Your AI team</strong>
          <p>Module specialists and read-only tools, powered by ProtoLink.</p>
          <b>↗</b>
        </Link>
        <Link to="/developers/architecture">
          <span className="doc-card-index">03</span>
          <strong>Under the hood</strong>
          <p>Explore the Python services, API contracts, and extension points.</p>
          <b>↗</b>
        </Link>
      </div>
    </div>
  );
}
