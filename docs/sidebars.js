/** Each top-level section owns a sidebar; chapters stay visible while reading. */
function chapter(label, description, items) {
  return { type: 'category', label, description, collapsible: false, items };
}

function section(label, slug, description, items) {
  return {
    type: 'category',
    label,
    collapsible: false,
    className: 'doc-section-sidebar',
    link: { type: 'generated-index', slug, title: label, description },
    items,
  };
}

module.exports = {
  gettingStarted: ['intro', 'getting-started/installation', 'getting-started/configuration'],
  userGuide: [
    section(
      'User guide',
      '/guides',
      'Find your workflow, from connecting an account to testing a strategy or asking Sibyl.',
      [
        chapter(
          'Accounts and setup',
          'Connect exchanges, configure Sibyl and understand your balances.',
          ['guides/account', 'guides/exchanges', 'guides/settings', 'guides/balance-checks'],
        ),
        chapter(
          'Markets and research',
          'Explore prices, statistics, news, Bitcoin activity and forecasts.',
          [
            'guides/markets',
            'guides/market-statistics',
            'guides/market-history',
            'guides/research',
            'guides/bitcoin-explorer',
            'guides/forecasting',
          ],
        ),
        chapter(
          'Trading and strategies',
          'Review orders, backtest ideas and monitor strategy runs.',
          [
            'guides/trading',
            'guides/strategies',
            'guides/strategy-validation',
            'guides/strategy-monitor',
            'guides/strategy-execution',
            'guides/portfolio-limits',
          ],
        ),
        chapter('Sibyl and AI', 'Meet the AI team, connect Telegram and run a local model.', [
          'guides/sibyl',
          'guides/oracle',
          'guides/telegram',
          'guides/ollama',
        ]),
        chapter(
          'Alerts and workspace',
          'Set up alerts and understand privacy and feature coverage.',
          ['guides/alerts', 'guides/account-risk', 'guides/security', 'guides/feature-coverage'],
        ),
      ],
    ),
  ],
  developers: [
    section(
      'Developers',
      '/developers',
      'Understand the architecture, follow the domain contracts and extend the Python backend and ProtoLink team.',
      [
        chapter(
          'Foundations',
          'Architecture, API contracts, extension points, testing and deployment.',
          [
            'developers/architecture',
            'developers/api',
            'developers/extending',
            'developers/testing',
            'developers/deployment',
            'developers/backend-roadmap',
          ],
        ),
        chapter(
          'Accounts and accounting',
          'Exchange adapters, synchronization, valuation and accounting evidence.',
          [
            'developers/accounts',
            'developers/exchange-clients',
            'developers/exchange-acceptance',
            'developers/account-sync',
            'developers/portfolio-valuation',
            'developers/account-performance',
            'developers/balance-checks',
            'developers/funding-effects',
          ],
        ),
        chapter(
          'Orders and funding',
          'Order lifecycle, funding imports, recovery and transfer reconciliation.',
          [
            'developers/order-management',
            'developers/order-reconciliation',
            'developers/order-recovery',
            'developers/order-discovery',
            'developers/funding-history',
            'developers/funding-pending-updates',
            'developers/funding-recent-sync',
            'developers/transfer-reconciliation',
            'developers/transfer-cost-basis',
            'developers/transfer-fees',
          ],
        ),
        chapter(
          'Research and data',
          'Market feeds, candle history, news, forecasting and Bitcoin research.',
          [
            'developers/market-data',
            'developers/provider-control',
            'developers/candle-history',
            'developers/news',
            'developers/forecasting',
            'developers/bitcoin-explorer',
          ],
        ),
        chapter(
          'Strategies and risk',
          'Research engines, execution controls, limits and persistent alerts.',
          [
            'developers/strategy-research',
            'developers/strategy-controls',
            'developers/portfolio-limits',
            'developers/alerts',
            'developers/account-risk',
          ],
        ),
        chapter(
          'ProtoLink agents',
          'Native agent lifecycle, model selection, metrics and acceptance checks.',
          [
            'developers/agents',
            'developers/agent-models',
            'developers/protolink-metrics',
            'developers/agent-acceptance',
          ],
        ),
      ],
    ),
  ],
  releases: ['changelog'],
};
