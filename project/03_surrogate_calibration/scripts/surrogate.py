"""Gaussian-process surrogate, Bayesian calibration and next-run proposals.

Inputs: knob values scaled to [0, 1] (config.json "knobs" ranges).
Outputs: the steady features listed in config.json "targets".

fit()       One Gaussian process (GP) per feature: constant x Matern-5/2 with
            one length scale per knob (ARD) + white noise. Replicate runs
            tell the GP how noisy the solver is. A short length scale for a
            knob = that knob matters for that feature.
posterior() Bayesian calibration on a large quasi-random sample of knob
            values: weight = exp(-1/2 sum_k (mu_k - y_k)^2 / (tol_k^2 + s_k^2))
            (mu, s: GP mean and std; y, tol: Huang target and tolerance),
            uniform prior, down-weighted near crashed runs. Gives posterior
            mean / std per knob and the best (highest weight) point.
propose()   Next run: posterior-weighted uncertainty sampling,
            score = sqrt(weight) * GP uncertainty, kept away from runs that
            are done, running or crashed. Every explore_every-th proposal is a
            space-filling point instead (guards against a wrong early fit).
converged() Stop test (see config "stop").
"""
import warnings

import numpy as np
from scipy.stats import qmc
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

N_SAMPLES = 16384
FAIL_RADIUS = 0.08     # scaled units: region around a crashed run avoided
MIN_DIST = 0.06        # scaled units: no new run this close to an existing one


def scale(cfg, params):
    """dict or list of dicts of knob values -> array in [0, 1]."""
    ks = cfg["knobs"]
    rows = [params] if isinstance(params, dict) else params
    return np.array([[(r[k["name"]] - k["low"])/(k["high"] - k["low"]) for k in ks]
                     for r in rows])


def unscale(cfg, u):
    return {k["name"]: float(k["low"] + ui*(k["high"] - k["low"]))
            for k, ui in zip(cfg["knobs"], u)}


def initial_design(cfg):
    """Latin hypercube + nominal point, nominal repeated n_replicates times."""
    d = cfg["design"]
    nom = {k["name"]: k["nominal"] for k in cfg["knobs"]}
    lhs = qmc.LatinHypercube(d=len(cfg["knobs"]), seed=d["seed"]).random(d["n_initial"] - 1)
    pts = [nom] + [unscale(cfg, u) for u in lhs] + [nom]*d["n_replicates"]
    tags = ["nominal"] + ["lhs"]*(d["n_initial"] - 1) + ["replicate"]*d["n_replicates"]
    return list(zip(pts, tags))


def target_names(cfg):
    return [k for k in cfg["targets"] if not k.startswith("_")]


class Surrogate:
    def __init__(self, cfg):
        self.cfg = cfg
        self.names = target_names(cfg)
        self.y = np.array([cfg["targets"][n]["value"] for n in self.names])
        self.tol = np.array([cfg["targets"][n]["tol"] for n in self.names])
        self.gps = {}
        self.X = None

    def fit(self, X, Y):
        """X: (n, d) scaled inputs, Y: (n, m) features in target order."""
        self.X = np.asarray(X, float)
        d = self.X.shape[1]
        for j, n in enumerate(self.names):
            y = np.asarray(Y[:, j], float)
            mu, sd = y.mean(), max(y.std(), 1e-6)
            kern = (ConstantKernel(1.0, (1e-2, 1e2))
                    * Matern(length_scale=np.full(d, 0.5), length_scale_bounds=(0.05, 20.0), nu=2.5)
                    + WhiteKernel(0.05, (1e-4, 1.0)))
            gp = GaussianProcessRegressor(kern, normalize_y=False, n_restarts_optimizer=4,
                                          random_state=0)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                gp.fit(self.X, (y - mu)/sd)
            self.gps[n] = (gp, mu, sd)
        return self

    def predict(self, U):
        """Mean and std (n, m) in physical units."""
        M, S = [], []
        for n in self.names:
            gp, mu, sd = self.gps[n]
            m, s = gp.predict(U, return_std=True)
            M.append(m*sd + mu); S.append(s*sd)
        return np.array(M).T, np.array(S).T

    def relevance(self):
        """Per feature and knob: 1/length scale (bigger = knob matters more)."""
        out = {}
        for n in self.names:
            k = self.gps[n][0].kernel_.k1.k2
            out[n] = (1.0/np.atleast_1d(k.length_scale)).tolist()
        return out

    def noise(self):
        """Fitted run-to-run noise std per feature (physical units)."""
        return {n: float(np.sqrt(self.gps[n][0].kernel_.k2.noise_level)*self.gps[n][2])
                for n in self.names}

    def posterior(self, failed_U=(), seed=0):
        d = self.X.shape[1]
        U = qmc.Sobol(d, seed=seed).random(N_SAMPLES)
        M, S = self.predict(U)
        var = self.tol**2 + S**2
        logw = -0.5*np.sum((M - self.y)**2/var + np.log(var), axis=1)
        for f in failed_U:
            logw += np.log1p(-np.exp(-np.sum((U - f)**2, axis=1)/(2*FAIL_RADIUS**2)) + 1e-12)
        w = np.exp(logw - logw.max()); w /= w.sum()
        mean = w @ U
        std = np.sqrt(w @ (U - mean)**2)
        best = U[np.argmax(w)]
        ess = 1.0/np.sum(w**2)
        Mb, Sb = self.predict(best[None])
        return {"U": U, "w": w, "M": M, "S": S, "mean": mean, "std": std, "best": best,
                "ess": float(ess), "best_pred": Mb[0], "best_pred_std": Sb[0]}

    def propose(self, post, taken_U, explore=False, seed=0):
        """One new scaled point, away from taken_U (done + running + failed)."""
        rng = np.random.default_rng(seed)
        U = post["U"]
        taken = np.atleast_2d(np.asarray(taken_U, float)) if len(taken_U) else np.zeros((0, U.shape[1]))
        dmin = (np.min(np.linalg.norm(U[:, None, :] - taken[None], axis=2), axis=1)
                if len(taken) else np.full(len(U), 1.0))
        if explore:
            # space filling: the sample point farthest from everything taken
            cand = rng.choice(len(U), 2048, replace=False)
            return U[cand[np.argmax(dmin[cand])]]
        unc = np.sqrt(np.sum(post["S"]**2/self.tol**2, axis=1))
        score = np.sqrt(post["w"])*unc*(1.0 - np.exp(-dmin**2/(2*MIN_DIST**2)))
        return U[np.argmax(score)]


def converged(cfg, post, rel, n_done):
    """True when every knob that matters is pinned down to < frac of its range.

    A knob 'matters' if, for some feature, its relevance (range/length scale)
    is >= 1 (the feature changes by about one GP length over the range).
    Insensitive knobs cannot be pinned down and are not waited for.
    """
    st = cfg["stop"]
    if n_done < st["min_runs"]:
        return False, "fewer than min_runs finished"
    matters = np.max(np.array(list(rel.values())), axis=0) >= 1.0
    if not matters.any():
        return False, "no knob seems to affect the targets yet (check ranges / data)"
    wide = [k["name"] for k, m, s in zip(cfg["knobs"], matters, post["std"])
            if m and s > st["posterior_std_frac"]]
    if wide:
        return False, "still uncertain: " + ", ".join(wide)
    return True, "all relevant knobs within {:.0%} of range".format(st["posterior_std_frac"])
