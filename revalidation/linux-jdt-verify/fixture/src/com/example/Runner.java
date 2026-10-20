package com.example;

public class Runner {
    public String run() {
        Greeter g = new Greeter();
        return g.greet("ci") + g.greet();
    }
}
