// Hanjie 参数化数字样机（单位：mm）。
// 官方尺寸与设计假设见 cad/parametric/geometry.json 和 docs/05-design-assumptions.md。
// 用法：在 OpenSCAD 中修改 part = "assembly" / "seat" / "fixture" 后渲染。

part = "assembly";
$fn = 96;

shell_od = 160;
shell_h = 200;
shell_t = 5;
bore_d = 40;
seat_core_od = 82;
seat_h = 12;
wing_ro = 73.8;
wing_width = 18;
slot_width = 4;
layout = 6;

module ring(outer_d, inner_d, height) {
    difference() {
        cylinder(d=outer_d, h=height);
        translate([0, 0, -0.1]) cylinder(d=inner_d, h=height + 0.2);
    }
}

module flexible_seat(points=layout) {
    wing_length = wing_ro - seat_core_od / 2;
    difference() {
        union() {
            ring(seat_core_od, bore_d, seat_h);
            for (i = [0:points-1]) {
                rotate([0, 0, i * 360 / points])
                    translate([seat_core_od / 2 + wing_length / 2, 0, 0])
                        cube([wing_length, wing_width, seat_h], center=true);
            }
        }
        // 径向柔顺槽：不切入中心刚性区，隔断周向收缩路径。
        for (i = [0:points-1]) {
            rotate([0, 0, i * 360 / points + 360 / points / 2])
                translate([seat_core_od / 2 + (wing_ro-seat_core_od/2)/2, 0, -0.1])
                    cube([wing_length, slot_width, seat_h + 0.2], center=true);
        }
    }
}

module shell() {
    difference() {
        cylinder(d=shell_od, h=shell_h);
        translate([0, 0, -0.1]) cylinder(d=shell_od - 2 * shell_t, h=shell_h + 0.2);
    }
}

module fixture() {
    // 刚性定位基准 + 可释放周向夹紧的数字样机表达。
    cylinder(d=190, h=8);
    translate([0, 0, 8]) cylinder(d=39.96, h=28);
    for (i = [0:5]) {
        rotate([0, 0, i * 60])
            translate([86, 0, 18]) cylinder(d=10, h=30);
    }
}

module assembly() {
    color("#b8c4ce", 0.35) shell();
    translate([0, 0, 100]) color("#d19a58", 1.0) flexible_seat();
    translate([0, 0, -8]) color("#59636e", 0.9) fixture();
}

if (part == "shell") shell();
else if (part == "seat") flexible_seat();
else if (part == "fixture") fixture();
else assembly();

