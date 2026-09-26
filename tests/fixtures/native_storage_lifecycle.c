/* Exercise the actual patch functions with deterministic native resource stubs. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef void *mp_obj_t;
#define mp_const_none NULL
#define MP_OBJ_TO_PTR(p) (p)
#define MP_ERROR_TEXT(p) (p)
#define MICROPY_HW_SPI_MAX 2
#define SDCARD_CARD_FLAGS_HOST_INIT_DONE 1
#define SDMMC_HOST_FLAG_DEINIT_ARG 1
static const int mp_type_OSError = 0;
static void mp_raise_msg(const int *type, const char *message) { (void)type; (void)message; abort(); }
static void *m_realloc(void *pointer, size_t size) {
    void *result = realloc(pointer, size);
    assert(result || !size);
    return result;
}

typedef struct bus mp_machine_hw_spi_bus_obj_t;
typedef struct device mp_machine_hw_spi_device_obj_t;
struct device {
    void *base;
    bool active;
    mp_machine_hw_spi_bus_obj_t *spi_bus;
    void (*deinit)(mp_machine_hw_spi_device_obj_t *);
};
struct bus {
    uint8_t device_count;
    mp_machine_hw_spi_device_obj_t **devices;
    void (*deinit)(mp_machine_hw_spi_bus_obj_t *);
    bool hardware_active;
};
typedef struct {
    union { void *base; mp_machine_hw_spi_device_obj_t spi_device; };
    int flags;
    int sdspi_handle;
    struct { int flags, slot; int (*deinit_p)(int); int (*deinit)(void); } host;
} sdcard_card_obj_t;

static mp_obj_t *machine_hw_spi_bus_objs;
static unsigned slot_removals[4];
static unsigned bus_releases;
static int sdspi_host_remove_device(int slot) {
    assert(slot >= 0 && slot < 4);
    ++slot_removals[slot];
    return 0;
}
static void check_esp_err(int result) { assert(result == 0); }
static void machine_hw_spi_bus_deinit_internal(mp_machine_hw_spi_bus_obj_t *bus) {
    if (!bus->hardware_active) return;
    for (unsigned i = 0; i < bus->device_count; ++i) {
        bus->devices[i]->deinit(bus->devices[i]);
    }
    bus->device_count = 0;
    bus->hardware_active = false;
    ++bus_releases;
}

typedef struct { int initialized; } lv_global_t;
static void *state_mp_lv_roots;
static void *state_mp_lv_user_data;
static void *mp_lv_roots;
#define MP_STATE_VM(name) state_##name
#define m_new0(type, count) ((type *)calloc((count), sizeof(type)))

#include "storage_patch_under_test.h"

static sdcard_card_obj_t card(mp_machine_hw_spi_bus_obj_t *bus, int slot) {
    sdcard_card_obj_t result = {0};
    result.spi_device.spi_bus = bus;
    result.spi_device.active = true;
    result.spi_device.deinit = sd_spi_deinit_callback;
    result.sdspi_handle = slot;
    result.flags = SDCARD_CARD_FLAGS_HOST_INIT_DONE;
    return result;
}

int main(void) {
    mp_lv_init_gc();
    void *first_vm_roots = mp_lv_roots;
    assert(first_vm_roots && first_vm_roots == state_mp_lv_roots);
    mp_lv_init_gc();
    assert(mp_lv_roots == first_vm_roots);
    state_mp_lv_user_data = first_vm_roots;
    /* mp_init does not reset custom VM roots; exercise the actual reset hook. */
    reset_lv_roots();
    assert(!mp_lv_roots && !state_mp_lv_roots && !state_mp_lv_user_data);
    mp_lv_init_gc();
    assert(mp_lv_roots && mp_lv_roots != first_vm_roots && mp_lv_roots == state_mp_lv_roots);
    free(first_vm_roots);
    free(mp_lv_roots);

    mp_machine_hw_spi_bus_obj_t bus = {.deinit = machine_hw_spi_bus_deinit_internal,
                                      .hardware_active = true};
    sdcard_card_obj_t a = card(&bus, 1), b = card(&bus, 2), foreign = card(&bus, 3);
    assert((void *)&a == (void *)&a.spi_device); /* Registered pointer is a GC head. */
    mp_machine_hw_spi_bus_add_device(&a.spi_device);
    mp_machine_hw_spi_bus_add_device(&b.spi_device);
    mp_machine_hw_spi_bus_add_device(&a.spi_device);
    assert(bus.device_count == 2 && bus.devices[0] == &a.spi_device && bus.devices[1] == &b.spi_device);
    mp_machine_hw_spi_bus_remove_device(&foreign.spi_device);
    assert(bus.device_count == 2);

    sd_deinit(&a);
    assert(slot_removals[1] == 1 && !a.flags && !a.spi_device.active);
    assert(bus.device_count == 1 && bus.devices[0] == &b.spi_device && bus.hardware_active);
    sd_deinit(&a); /* A later finalizer cannot remove B's slot. */
    assert(slot_removals[1] == 1 && slot_removals[2] == 0 && bus.device_count == 1);

    mp_obj_t registry[2] = {&bus, NULL};
    machine_hw_spi_bus_objs = registry;
    mp_machine_hw_spi_bus_deinit_all();
    assert(machine_hw_spi_bus_objs == NULL && !bus.hardware_active && bus.device_count == 0);
    assert(slot_removals[2] == 1 && !b.flags && !b.spi_device.active && bus_releases == 1);
    sd_deinit(&b); /* gc_sweep_all follows native reset cleanup. */
    mp_machine_hw_spi_bus_deinit_all();
    assert(slot_removals[2] == 1 && bus_releases == 1);

    bus.hardware_active = true;
    sdcard_card_obj_t reopened = card(&bus, 2);
    mp_machine_hw_spi_bus_add_device(&reopened.spi_device);
    sd_deinit(&a);
    sd_deinit(&b);
    assert(bus.device_count == 1 && reopened.spi_device.active && slot_removals[2] == 1);
    sd_deinit(&reopened);
    assert(slot_removals[2] == 2 && bus_releases == 2 && bus.device_count == 0);
    free(bus.devices);
    puts("native storage lifecycle: passed");
    return 0;
}
