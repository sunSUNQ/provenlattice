#pragma once

namespace demo {
class Service {
public:
    int run(int value) const;
    int run(double value) const;
};
}

using DemoService = demo::Service;
