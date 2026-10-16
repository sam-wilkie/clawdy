use std::ffi::OsStr;

#[derive(Debug, PartialEq, Eq)]
enum Decision {
    Disabled,
    ExitNow,
    Watch(u32),
}

fn decision(value: Option<&OsStr>) -> Decision {
    match value {
        None => Decision::Disabled,
        Some(value) => match value
            .to_str()
            .filter(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit()))
            .and_then(|s| s.parse::<u32>().ok())
            .filter(|pid| *pid > 0)
        {
            Some(pid) => Decision::Watch(pid),
            None => Decision::ExitNow,
        },
    }
}

// The injected wait returns when the parent is gone or cannot be opened.
fn supervise(action: Decision, wait: impl FnOnce(u32), exit: impl FnOnce()) {
    match action {
        Decision::Disabled => return,
        Decision::ExitNow => (),
        Decision::Watch(pid) => wait(pid),
    }
    exit();
}

#[cfg(windows)]
fn wait_for_parent(pid: u32) {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{OpenProcess, WaitForSingleObject, INFINITE, PROCESS_SYNCHRONIZE},
    };
    // SYNCHRONIZE is sufficient; the handle stays bound to this process across PID reuse.
    unsafe {
        let handle = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
        if !handle.is_null() {
            WaitForSingleObject(handle, INFINITE);
            CloseHandle(handle);
        }
    }
}

#[cfg(windows)]
pub fn start(exit: impl FnOnce() + Send + 'static) {
    let value = std::env::var_os("CLAWDY_PARENT_PID");
    let action = decision(value.as_deref());
    if action != Decision::Disabled {
        std::thread::spawn(move || supervise(action, wait_for_parent, exit));
    }
}

#[cfg(not(windows))]
pub fn start(_: impl FnOnce() + Send + 'static) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unset_means_no_watchdog() {
        assert_eq!(decision(None), Decision::Disabled);
    }

    #[test]
    fn invalid_pid_means_exit_now() {
        for value in ["", "abc", "-1", "0", "4294967296", " 42", "+42"] {
            assert_eq!(decision(Some(OsStr::new(value))), Decision::ExitNow);
        }
    }

    #[test]
    fn valid_pid_means_watch() {
        assert_eq!(decision(Some(OsStr::new("42"))), Decision::Watch(42));
    }

    #[test]
    fn supervisor_waits_before_exit_and_skips_os_calls_when_not_watching() {
        use std::cell::RefCell;
        let events = RefCell::new(Vec::new());
        supervise(
            Decision::Disabled,
            |_| panic!("must not wait"),
            || panic!("must not exit"),
        );
        supervise(
            Decision::ExitNow,
            |_| panic!("must not wait"),
            || events.borrow_mut().push("exit"),
        );
        assert_eq!(*events.borrow(), ["exit"]);
        events.borrow_mut().clear();
        // An immediate return also models OpenProcess failing for an already-gone parent.
        supervise(
            Decision::Watch(42),
            |pid| {
                assert_eq!(pid, 42);
                events.borrow_mut().push("wait");
            },
            || events.borrow_mut().push("exit"),
        );
        assert_eq!(*events.borrow(), ["wait", "exit"]);
    }
}
