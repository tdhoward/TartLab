/* Exercise the actual patch's cleanup scopes with NLR-style exception jumps. */
#include <assert.h>
#include <stdbool.h>
#include <setjmp.h>
#include <stdio.h>
#include <stddef.h>

typedef struct node {
    struct node *prev;
    void (*fun)(void *);
} nlr_jump_callback_node_t;
static nlr_jump_callback_node_t *top;
static jmp_buf boundary;
static nlr_jump_callback_node_t *boundary_top;

static void nlr_push_jump_callback(nlr_jump_callback_node_t *node, void (*fun)(void *)) {
    node->prev = top;
    node->fun = fun;
    top = node;
}
static void nlr_pop_jump_callback(bool run) {
    nlr_jump_callback_node_t *node = top;
    top = node->prev;
    if (run) node->fun(node);
}
static void raise_exception(void) {
    while (top != boundary_top) nlr_pop_jump_callback(true);
    longjmp(boundary, 1);
}

#include "lvgl_callback_under_test.h"

static void success(void) { assert(_nesting == 1); }
static void failure(void) { assert(_nesting >= 1); raise_exception(); }
static void nested_failure(void) { invoke(failure); }
static void local_catch(void) {
    assert(_nesting == 1);
    boundary_top = top;
    if (setjmp(boundary) == 0) {
        invoke(failure);
        assert(false);
    }
    assert(_nesting == 1);
}

int main(void) {
    invoke(success);
    assert(_nesting == 0 && top == NULL);
    assert(invoke_return() == 42);
    assert(_nesting == 0 && top == NULL);
    for (int nested = 0; nested < 2; ++nested) {
        boundary_top = NULL;
        if (setjmp(boundary) == 0) {
            invoke(nested ? nested_failure : failure);
            assert(false);
        }
        assert(_nesting == 0 && top == NULL);
    }
    invoke(local_catch);
    assert(_nesting == 0 && top == NULL);
    /* Teardown also recovers state leaked by older/unprotected entry points. */
    _nesting = 1;
    mp_lv_reset_callback_state();
    assert(_nesting == 0);
    invoke(success);
    puts("native LVGL callback cleanup: passed");
}
