import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import { GuideIcon, ProviderMark } from './Marks';
import integrations from './integrations.json';

/** A public catalog, with implementation scope kept separate from brand recognition. */
export default function IntegrationShowcase() {
  const assets = useBaseUrl('/img/integrations/');
  const telegram = integrations.messaging.find((channel) => channel.available);
  return (
    <section className="sibyl-connect-section sibyl-home-width" aria-labelledby="connect-heading">
      <div className="sibyl-section-heading">
        <div>
          <span className="sibyl-section-kicker">YOUR WORLD, CONNECTED</span>
          <h2 id="connect-heading">Bring your world into focus.</h2>
        </div>
        <p>
          Your exchanges. Your choice of intelligence.
          <br /> A conversation that travels with you.
        </p>
      </div>
      <div className="sibyl-connect-panel sibyl-exchange-panel">
        <div className="sibyl-connect-panel-heading">
          <div>
            <span className="sibyl-connect-icon">
              <GuideIcon name="account" />
            </span>
            <h3>
              Exchanges <span>{integrations.exchanges.length}</span>
            </h3>
          </div>
          <Link to="/guides/exchanges">
            Explore coverage <GuideIcon name="arrow" />
          </Link>
        </div>
        <ul className="sibyl-exchange-list">
          {integrations.exchanges.map((exchange) => (
            <li key={exchange.id}>
              <img
                src={`${assets}${exchange.image}`}
                alt=""
                width="26"
                height="26"
                loading="lazy"
              />
              <span>{exchange.name}</span>
            </li>
          ))}
        </ul>
        <p className="sibyl-connect-footnote">
          Account and trading capabilities vary by exchange. Also available:{' '}
          <Link to="/guides/exchanges#test-environments-and-orders">
            Binance Testnet and Coinbase Exchange Sandbox
          </Link>
          , plus an optional offline Demo account.
        </p>
      </div>
      <div className="sibyl-connect-columns">
        <div className="sibyl-connect-panel">
          <div className="sibyl-connect-panel-heading">
            <div>
              <span className="sibyl-connect-icon lilac">
                <GuideIcon name="spark" />
              </span>
              <h3>AI, your way</h3>
            </div>
            <Link to="/guides/settings#ai-models">
              Model setup <GuideIcon name="arrow" />
            </Link>
          </div>
          {['api', 'local'].map((kind) => (
            <div className="sibyl-model-group" key={kind}>
              <h4>
                {kind === 'api' ? 'API providers & compatible endpoints' : 'Local model runtimes'}
              </h4>
              <ul className="sibyl-model-list">
                {integrations.models
                  .filter((provider) => provider.kind === kind)
                  .map((provider) => (
                    <li key={provider.id}>
                      <ModelMark provider={provider} />
                      <span>{provider.name}</span>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
          <p className="sibyl-connect-footnote">
            Bring your own API key or run a local model. Models and inference servers are configured
            separately.
          </p>
        </div>
        <div className="sibyl-connect-panel sibyl-messaging-panel">
          <div className="sibyl-connect-panel-heading">
            <div>
              <span className="sibyl-connect-icon mint">
                <GuideIcon name="message" />
              </span>
              <h3>Sibyl, beyond the dashboard</h3>
            </div>
          </div>
          <p className="sibyl-connect-description">
            Talk to your AI team from a familiar app, through your running Sibyl backend.
          </p>
          <Link className="sibyl-telegram-link" to="/guides/telegram">
            <img src={`${assets}${telegram.image}`} width="38" height="38" alt="" loading="lazy" />
            <span>
              <strong>Telegram</strong>
              <span>Private bot conversations with Sibyl</span>
            </span>
            <span className="sibyl-available-badge">
              <i />
              Available
            </span>
            <GuideIcon name="arrow" />
          </Link>
          <h4 className="sibyl-planned-heading">
            Planned channels <span>Coming soon</span>
          </h4>
          <ul className="sibyl-channel-list">
            {integrations.messaging
              .filter((channel) => !channel.available)
              .map((channel) => (
                <li key={channel.id}>
                  {channel.image ? (
                    <img
                      src={`${assets}${channel.image}`}
                      width="23"
                      height="23"
                      alt=""
                      loading="lazy"
                    />
                  ) : (
                    <GuideIcon name="mail" />
                  )}
                  <span>{channel.name}</span>
                </li>
              ))}
          </ul>
          <p className="sibyl-connect-footnote">
            These channels are unavailable setup previews. Follow the{' '}
            <Link to="/developers/backend-roadmap#7-sibyl-and-protolink-workflows--partial">
              messaging checklist
            </Link>{' '}
            for implementation status.
          </p>
        </div>
      </div>
    </section>
  );
}

function ModelMark({ provider }) {
  const marks = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    gemini: 'Gemini',
    deepseek: 'DeepSeek',
    ollama: 'Ollama',
    grok: 'xAI',
    huggingface: 'Hugging Face',
    lmstudio: 'LM Studio',
    vllm: 'vLLM',
  };
  return marks[provider.id] ? (
    <ProviderMark name={marks[provider.id]} />
  ) : (
    <GuideIcon name={provider.id === 'llama.cpp-local' ? 'chip' : 'server'} />
  );
}
