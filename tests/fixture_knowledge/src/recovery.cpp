namespace storage {

class StorageRecovery {
 public:
  int retry(int attempt);
};

int StorageRecovery::retry(int attempt) {
  return attempt + 1;
}

int duplicate() { return 1; }

}  // namespace storage
