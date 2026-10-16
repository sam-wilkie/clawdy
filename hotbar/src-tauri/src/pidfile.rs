use std::{
    fs, io,
    path::{Path, PathBuf},
};

#[derive(Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct PidFile {
    pub pid: u32,
    pub exe: PathBuf,
}

pub fn read(path: &Path) -> Option<PidFile> {
    serde_json::from_slice(&fs::read(path).ok()?).ok()
}

pub fn write(path: &Path, record: &PidFile) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, serde_json::to_vec(record)?)
}

pub struct OwnedPidFile {
    pub path: PathBuf,
    pub record: PidFile,
}

impl OwnedPidFile {
    pub fn remove(&self) {
        if read(&self.path).as_ref() == Some(&self.record) {
            let _ = fs::remove_file(&self.path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_and_ignore_missing_or_corrupt_file() {
        let dir = std::env::temp_dir().join(format!("clawdy-pidfile-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hotbar.pid");
        let _ = std::fs::remove_file(&path);
        assert_eq!(read(&path), None);
        let record = PidFile {
            pid: 42,
            exe: "C:\\Clawdy\\clawdy-hotbar.exe".into(),
        };
        write(&path, &record).unwrap();
        assert_eq!(read(&path), Some(record));
        let json: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        assert_eq!(
            json,
            serde_json::json!({"pid": 42, "exe": "C:\\Clawdy\\clawdy-hotbar.exe"})
        );
        for corrupt in ["not JSON", "{}", "{\"pid\":\"42\",\"exe\":\"x\"}"] {
            std::fs::write(&path, corrupt).unwrap();
            assert_eq!(read(&path), None);
        }
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn remove_deletes_only_its_own_record() {
        let dir = std::env::temp_dir().join(format!("clawdy-pidfile-own-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("hotbar.pid");
        let mine = PidFile { pid: 1, exe: "a.exe".into() };
        let owned = OwnedPidFile { path: path.clone(), record: PidFile { pid: 1, exe: "a.exe".into() } };
        write(&path, &PidFile { pid: 2, exe: "a.exe".into() }).unwrap();
        owned.remove();
        assert!(path.exists(), "another instance's pidfile must survive");
        write(&path, &mine).unwrap();
        owned.remove();
        assert!(!path.exists());
        owned.remove(); // already gone: no panic
        std::fs::remove_dir_all(dir).unwrap();
    }
}
