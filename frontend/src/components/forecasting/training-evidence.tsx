import { Badge } from '../ui';
import { number } from '../../lib/api';
import type { ForecastDetail, HuberTraining, NeuralTraining } from '../../lib/forecast-types';

/** Training receipts explain fitting; independent test errors remain the accuracy evidence. */
export function ForecastTrainingEvidence({ report }: { report: ForecastDetail }) {
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
