import React from 'react';
import Link from '@docusaurus/Link';
import CrystalScene from './brand/CrystalScene';
import { GuideIcon, ProviderMark } from './brand/Marks';

const paths = [
  {
    number: '01',
    icon: 'account',
    title: 'Connect your world.',
    text: 'Bring your exchange accounts together. Start with one, connect more when you’re ready.',
    to: '/guides/exchanges',
    label: 'Connect your accounts',
  },
  {
    number: '02',
    icon: 'spark',
    title: 'Meet your AI team.',
    text: 'Get to know Sibyl and the ProtoLink specialists that bring context to your questions.',
    to: '/guides/sibyl',
    label: 'Meet the team',
  },
  {
    number: '03',
    icon: 'code',
    title: 'Make it your own.',
    text: 'Explore the Python API, native agent tools and the building blocks behind the workspace.',
    to: '/developers/architecture',
    label: 'Explore the architecture',
  },
];

const workspaces = [
  {
    icon: 'markets',
    title: 'Markets',
    text: 'Follow price, momentum and the story behind the chart.',
    to: '/guides/markets',
    color: 'blue',
  },
  {
    icon: 'strategies',
    title: 'Strategies',
    text: 'Test an idea. Inspect the evidence. Understand every decision.',
    to: '/guides/strategies',
    color: 'peach',
  },
  {
    icon: 'account',
    title: 'Account',
    text: 'A clearer view of your assets, across your exchanges.',
    to: '/guides/account',
    color: 'mint',
  },
  {
    icon: 'news',
    title: 'News',
    text: 'Source-linked reporting, sentiment and a little more context.',
    to: '/guides/research#reporter-news-and-insights',
    color: 'sand',
  },
  {
    icon: 'forecast',
    title: 'Forecasting',
    text: 'Train a model, measure its limits and explore what comes next.',
    to: '/guides/forecasting',
    color: 'lilac',
  },
  {
    icon: 'research',
    title: 'Research',
    text: 'Look closer at crypto projects, Bitcoin activity and equities.',
    to: '/guides/research',
    color: 'sky',
  },
];

/** A product-led entrance, with decorative motion kept separate from guide navigation. */
export default function BrandHero() {
  return (
    <>
      <section className="sibyl-home-hero" aria-labelledby="sibyl-hero-title">
        <div className="sibyl-home-width sibyl-hero-grid">
          <div className="sibyl-hero-copy">
            <Link className="doc-welcome-badge" to="/changelog">
              <span className="doc-release-dot" /> Meet Sibyl 2.1 <span aria-hidden="true">↗</span>
            </Link>
            <h1 id="sibyl-hero-title">
              <span>Read the signals.</span>
              <span className="sibyl-hero-accent">See the bigger picture.</span>
            </h1>
            <p>
              Your exchanges, your research, your AI team.
              <br className="hero-desktop-break" /> One connected workspace. A little more clarity.
            </p>
            <div className="sibyl-hero-actions">
              <Link className="sibyl-doc-button" to="/welcome">
                Get started <GuideIcon name="arrow" />
              </Link>
              <Link className="sibyl-doc-secondary" to="/guides">
                Explore the guides <span aria-hidden="true">↗</span>
              </Link>
            </div>
            <div className="sibyl-hero-principles">
              <span>
                <GuideIcon name="shield" /> Local-first
              </span>
              <span>
                <GuideIcon name="spark" /> ProtoLink inside
              </span>
              <span>
                <GuideIcon name="code" /> Open source
              </span>
            </div>
          </div>
          <CrystalScene />
        </div>
      </section>
      <section
        className="sibyl-integrations sibyl-home-width"
        aria-label="Exchange and AI integrations"
      >
        <div className="sibyl-integration-heading">
          <span>YOUR WORLD, CONNECTED</span>
          <p>
            Familiar names. <br />
            Your choice of AI.
          </p>
        </div>
        <div className="sibyl-integration-marks">
          {['Binance', 'Coinbase', 'Kraken', 'OpenAI', 'Anthropic', 'Ollama'].map((name) => (
            <div key={name}>
              <ProviderMark name={name} />
              <span>{name}</span>
            </div>
          ))}
        </div>
        <p className="sibyl-integration-note">
          Explore <Link to="/guides/exchanges">exchange coverage</Link> and{' '}
          <Link to="/guides/settings#ai-models">AI providers</Link>. Capabilities vary by
          integration.
        </p>
      </section>
      <section className="sibyl-start-section sibyl-home-width" aria-labelledby="start-heading">
        <div className="sibyl-section-heading">
          <div>
            <span className="sibyl-section-kicker">A PLACE TO BEGIN</span>
            <h2 id="start-heading">Find your way in.</h2>
          </div>
          <p>
            A first connection, a better question,
            <br />
            or a look under the hood.
          </p>
        </div>
        <div className="sibyl-doc-paths">
          {paths.map((path) => (
            <Link
              to={path.to}
              key={path.number}
              className={`sibyl-path-card sibyl-path-${path.number}`}
            >
              <div className="sibyl-path-top">
                <span className="doc-card-index">{path.number}</span>
                <GuideIcon name={path.icon} />
              </div>
              <h3>{path.title}</h3>
              <p>{path.text}</p>
              <span className="sibyl-card-link">
                {path.label}
                <GuideIcon name="arrow" />
              </span>
            </Link>
          ))}
        </div>
      </section>
      <section
        className="sibyl-workspaces-section sibyl-home-width"
        aria-labelledby="workspace-heading"
      >
        <div className="sibyl-section-heading">
          <div>
            <span className="sibyl-section-kicker">ROOM TO EXPLORE</span>
            <h2 id="workspace-heading">Follow your curiosity.</h2>
          </div>
          <Link className="sibyl-subtle-link" to="/guides">
            All workspace guides <GuideIcon name="arrow" />
          </Link>
        </div>
        <div className="sibyl-workspace-grid">
          {workspaces.map((workspace) => (
            <Link className="sibyl-workspace-card" to={workspace.to} key={workspace.title}>
              <span className={`sibyl-workspace-icon ${workspace.color}`}>
                <GuideIcon name={workspace.icon} />
              </span>
              <div>
                <h3>{workspace.title}</h3>
                <p>{workspace.text}</p>
              </div>
              <GuideIcon name="arrow" className="sibyl-workspace-arrow" />
            </Link>
          ))}
        </div>
      </section>
      <section className="sibyl-home-outro sibyl-home-width">
        <div>
          <span className="sibyl-section-kicker">ON YOUR TERMS</span>
          <h2>
            Start small.
            <br />
            Connect the rest as you go.
          </h2>
          <p>
            Explore public research or a clearly labeled Demo preview.
            <br />
            Connect your accounts when you’re ready.
          </p>
        </div>
        <div className="sibyl-outro-actions">
          <Link className="sibyl-doc-button" to="/getting-started/installation">
            Make yourself at home <GuideIcon name="arrow" />
          </Link>
          <Link className="sibyl-subtle-link" to="/guides/security">
            Your data, your workspace <GuideIcon name="shield" />
          </Link>
        </div>
      </section>
    </>
  );
}
