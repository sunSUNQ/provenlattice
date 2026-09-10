#include "api.hpp"

namespace demo {
int Service::run(int value) const { return value + 1; }
int Service::run(double value) const { return static_cast<int>(value); }
}
