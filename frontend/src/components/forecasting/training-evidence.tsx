import { Badge } from '../ui';
import { number } from '../../lib/api';
import type { ForecastDetail, HuberTraining, NeuralTraining } from '../../lib/forecast-types';

/** Training receipts explain fitting; independent test errors remain the accuracy evidence. */
export function ForecastTrainingEvidence({ report }: { report: ForecastDetail }) {
  if (report.arima_training) return <ARIMAEvidence report={report} />;
  if (!report.training?.length) return null;
  const huber = report.model.parameters.family === 'huber';
  const robust = report.training.filter((fit): fit is HuberTraining => fit.family === 'huber');
  const neural = report.training.filter((fit): fit is NeuralTraining => fit.family !== 'huber');
  return (
    <details className="forecast-advanced">
      <summary>{huber ? 'Huber training evidence' : 'Neural training evidence'}</summary>
      <p className="footnote">
        {huber
          ? 'Each horizon uses training-only median/MAD target scaling and fixed-scale Huber loss. Large residuals receive smaller positive weights; observations are never deleted. The optimizer stops on training coefficient change or its 60-step limit. Losses are standardized separately per horizon; compare held-out price errors rather than ranking these losses.'
          : 'Training objective only · lower loss does not establish held-out skill. Fixed iterations; the test window never chooses weights.'}
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Horizon</th>
              {huber ? (
                <>
                  <th>Delta / return threshold</th>
                  <th>Optimizer</th>
                  <th>Downweighted</th>
                  <th>Effective weight</th>
                  <th>Initial → final loss</th>
                </>
              ) : (
                <>
                  <th>Architecture</th>
                  <th>Optimizer</th>
                  <th>Initial loss</th>
                  <th>Final loss</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {huber
              ? robust.map((fit) => (
                  <tr key={fit.horizon}>
                    <td>{fit.horizon}d</td>
                    <td>
                      {fit.delta}
                      <br />
                      <small>{number(fit.residual_threshold, 6)} log-return units</small>
                    </td>
                    <td>
                      {fit.steps}/{fit.max_steps} IRLS steps
                      <br />
                      <Badge tone={fit.converged ? 'lime' : 'sand'}>
                        {fit.converged ? 'Converged' : 'Step limit reached'}
                      </Badge>
                    </td>
                    <td>
                      {fit.downweighted_samples}/{fit.training_samples}
                    </td>
                    <td>
                      {number(fit.effective_weight_sum, 2)}
                      <br />
                      <small>Min weight {number(fit.minimum_weight, 5)}</small>
                    </td>
                    <td>
                      {number(fit.initial_loss, 6)} → {number(fit.final_loss, 6)}
                    </td>
                  </tr>
                ))
              : neural.map((fit) => (
                  <tr key={fit.horizon}>
                    <td>{fit.horizon}d</td>
                    <td>{fit.hidden_units} tanh units</td>
                    <td>
                      {fit.epochs} steps · {fit.optimizer}
                    </td>
                    <td>{number(fit.initial_loss, 5)}</td>
                    <td>{number(fit.final_loss, 5)}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {huber && (
        <p className="footnote">
          Downweighting is a property of the fitted loss, not a claim that a market observation is
          wrong. Extreme feature leverage and genuine market shocks can still affect the model.
          Step-limit fits are retained as unconverged; neither convergence nor lower training loss
          guarantees future accuracy.
        </p>
      )}
    </details>
  );
}

function ARIMAEvidence({ report }: { report: ForecastDetail }) {
  const fit = report.arima_training!;
  const params = report.model.parameters;
  return (
    <details className="forecast-advanced">
      <summary>{params.arima_season ? 'Weekly SARIMA' : 'ARIMA'} training evidence</summary>
      <p className="footnote">
        {params.arima_season ? 'SARIMA' : 'ARIMA'}({params.arima_p},1,{params.arima_q})
        {params.arima_season ? ' × (1,0,0,7)' : ''} · {fit.library} {fit.library_version}. One
        training-only fit serves all horizons. Parameters stay fixed while the native filter
        processes the latest 90 observed closes at each origin; no future-price smoothing or
        test-driven order search.
      </p>
      <div className="forecast-partitions forecast-arima-evidence">
        <div>
          <span>Fit status</span>
          <strong>{fit.converged ? 'Converged' : 'Not converged'}</strong>
          <small>
            {fit.iterations}/{fit.max_iterations} optimizer iterations
          </small>
        </div>
        <div>
          <span>Training returns</span>
          <strong>{fit.training_returns}</strong>
          <small>{fit.estimator}</small>
        </div>
        <div>
          <span>AIC / BIC</span>
          <strong>
            {number(fit.aic, 2)} / {number(fit.bic, 2)}
          </strong>
          <small>Training fit criteria</small>
        </div>
        <div>
          <span>Log likelihood</span>
          <strong>{number(fit.log_likelihood, 2)}</strong>
          <small>{fit.scale_units}</small>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Native parameter</th>
              <th>Fitted value</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(fit.parameter_values).map(([name, value]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{number(value, 6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {fit.warning_categories.length > 0 && (
        <p className="footnote">
          Fit warnings: {fit.warning_categories.join(', ')}. Inspect independent test results before
          interpreting this model.
        </p>
      )}
      <p className="footnote">
        Convergence, likelihood and information criteria describe training fit, not future accuracy.
        AIC/BIC are comparable only on identical training observations and scaling. Compare held-out
        price errors, naïve/drift benchmarks and empirical band coverage. Bands use held-out
        residuals, not the library’s Gaussian intervals.
      </p>
    </details>
  );
}
