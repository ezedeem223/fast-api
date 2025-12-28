use once_cell::sync::Lazy;
use pyo3::prelude::*;

static MAX_SCORE: f64 = 100.0;

fn clamp_score(score: f64) -> f64 {
    if score < 0.0 {
        0.0
    } else if score > MAX_SCORE {
        MAX_SCORE
    } else {
        score
    }
}

fn engagement_core(likes: i64, comments: i64) -> f64 {
    let raw = (likes as f64) + (comments as f64) * 2.0;
    if raw <= 0.0 {
        return 0.0;
    }
    clamp_score((raw + 1.0).ln() * 20.0)
}

fn quality_core(content: &str) -> f64 {
    let mut score = 0.0_f64;
    let len = content.chars().count();
    if (50..=2000).contains(&len) {
        score += 40.0;
    } else if len > 2000 {
        score += 20.0;
    }
    if content.contains('\n') {
        score += 10.0;
    }
    let words: Vec<&str> = content.split_whitespace().collect();
    if !words.is_empty() {
        let unique = words.iter().collect::<std::collections::HashSet<_>>();
        let diversity = unique.len() as f64 / words.len() as f64;
        if diversity > 0.6 {
            score += 30.0;
        } else if diversity > 0.4 {
            score += 15.0;
        }
    }
    score += 20.0;
    clamp_score(score)
}

#[pyfunction]
fn engagement_score(likes: i64, comments: i64) -> PyResult<f64> {
    Ok(engagement_core(likes, comments))
}

#[pyfunction]
fn quality_score(content: &str) -> PyResult<f64> {
    Ok(quality_core(content))
}

#[pymodule]
fn social_economy_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(engagement_score, m)?)?;
    m.add_function(wrap_pyfunction!(quality_score, m)?)?;
    Ok(())
}
