#include "api.hpp"

namespace app {
int execute(demo::Service& service) {
    return service.run(1);
}
}
